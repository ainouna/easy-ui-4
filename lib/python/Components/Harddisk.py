import os
import time
from Tools.CList import CList
from SystemInfo import SystemInfo
from Components.Console import Console
from boxbranding import getMachineName, getMachineBuild
import Task
from About import getModelString
import re
import subprocess

def readFile(filename):
	file = open(filename)
	data = file.read().strip()
	file.close()
	return data

def getPartitionNames():
	partitions = []
	try:
		f = open('/proc/partitions', 'r')
		for line in f.readlines():
			parts = line.strip().split()
			if not parts:
				continue
			device = parts[3]
			if device in partitions or not device[-1].isdigit():
				continue
			partitions.append(device)
	except IOError, ex:
		print "[Harddisk] Failed to open /proc/partitions", ex
	return partitions

def getRealFsType(dev, default):
	blkid = "blkid"
	try:
		p = subprocess.Popen((blkid, "-s", "TYPE", "-o", "value", dev), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except OSError as ex:
		print "[Harddisk] Could not run %s: %s" % (blkid, ex)
		return default
	output = map(str.splitlines, p.communicate())
	retcode = p.wait()
	if len(output[0]) == 1 and not output[1] and retcode == 0:
		return output[0][0]
	print "[Harddisk] %s returned bad output: %s" % (blkid, output)
	return default

def getProcMounts():
	try:
		mounts = open("/proc/mounts", 'r')
		result = []
		tmp = [line.strip().split(' ') for line in mounts]
		mounts.close()
		for item in tmp:
			# Spaces are encoded as \040 in mounts
			item[1] = item[1].replace('\\040', ' ')
			if item[2] == "fuseblk":
				item[2] = getRealFsType(item[0], item[2])
			result.append(item)
		return result
	except IOError, ex:
		print "[Harddisk] Failed to open /proc/mounts", ex
		return []

def isFileSystemSupported(filesystem):
	try:
		file = open('/proc/filesystems', 'r')
		for fs in file:
			if fs.strip().endswith(filesystem):
				file.close()
				return True
		file.close()
		return False
	except Exception, ex:
		print "[Harddisk] Failed to read /proc/filesystems:", ex

def findMountPoint(path):
	""" Example: findMountPoint("/media/hdd/some/file") returns "/media/hdd\" """
	path = os.path.abspath(path)
	while not os.path.ismount(path):
		path = os.path.dirname(path)
	return path


DEVTYPE_UDEV = 0
DEVTYPE_DEVFS = 1

class Harddisk:
	fsckOpts = {
		"ext2": ("fsck.ext2", "-D", "-f", "-p"),
		"ext3": ("fsck.ext3", "-D", "-f", "-p"),
		"ext4": ("fsck.ext4", "-D", "-f", "-p"),
		"vfat": ("fsck.vfat", "-p"),
	}

	def __init__(self, device, removable=False):
		self.device = device

		if os.access("/dev/.udev", 0):
			self.type = DEVTYPE_UDEV
		elif os.access("/dev/.devfsd", 0):
			self.type = DEVTYPE_DEVFS
		else:
			print "[Harddisk] Unable to determine structure of /dev"

		self.max_idle_time = 0
		self.idle_running = False
		self.last_access = time.time()
		self.last_stat = 0
		self.timer = None
		self.is_sleeping = False

		self.dev_path = ''
		self.disk_path = ''
		self.mount_path = None
		self.mount_device = None
		self.fs_type = None
		self.phys_path = os.path.realpath(self.sysfsPath('device'))

		if self.type == DEVTYPE_UDEV:
			self.dev_path = '/dev/' + self.device
			self.disk_path = self.dev_path

		elif self.type == DEVTYPE_DEVFS:
			tmp = readFile(self.sysfsPath('dev')).split(':')
			s_major = int(tmp[0])
			s_minor = int(tmp[1])
			for disc in os.listdir("/dev/discs"):
				dev_path = os.path.realpath('/dev/discs/' + disc)
				disk_path = dev_path + '/disc'
				try:
					rdev = os.stat(disk_path).st_rdev
				except OSError:
					continue
				if s_major == os.major(rdev) and s_minor == os.minor(rdev):
					self.dev_path = dev_path
					self.disk_path = disk_path
					break

		print "[Harddisk] new Harddisk", self.device, '->', self.dev_path, '->', self.disk_path
		if not removable:
			self.startIdle()

	def __lt__(self, ob):
		return self.device < ob.device

	def partitionPath(self, n):
		if self.type == DEVTYPE_UDEV:
			if self.dev_path.startswith('/dev/mmcblk'):
				return self.dev_path + "p" + n
			else:
				return self.dev_path + n
		elif self.type == DEVTYPE_DEVFS:
			return self.dev_path + '/part' + n

	def sysfsPath(self, filename):
		return os.path.join('/sys/block/', self.device, filename)

	def stop(self):
		if self.timer:
			self.timer.stop()
			self.timer.callback.remove(self.runIdle)

	def bus(self):
		ret = _("External")
		# SD/MMC(F1 specific)
		if self.type == DEVTYPE_UDEV:
			card = "sdhci" in self.phys_path
			type_name = " (SD/MMC)"
		# CF(7025 specific)
		elif self.type == DEVTYPE_DEVFS:
			card = self.device[:2] == "hd" and "host0" not in self.dev_path
			type_name = " (CF)"

		internal = any(x in self.phys_path for x in ("pci", "ahci"))

		if card:
			ret += type_name
		elif internal:
			ret = _("Internal")
		return ret

	def diskSize(self):
		cap = 0
		try:
			line = readFile(self.sysfsPath('size'))
			cap = int(line)
		except:
			dev = self.findMount()
			if dev:
				stat = os.statvfs(dev)
				cap = int(stat.f_blocks * stat.f_bsize)
				return cap / 1000 / 1000
			else:
				return cap
		return cap / 1000 * 512 / 1000

	def capacity(self):
		cap = self.diskSize()
		if cap == 0:
			return ""
		if cap < 1000:
			return _("%03d MB") % cap
		return _("%d.%03d GB") % (cap/1000, cap%1000)

	def model(self):
		try:
			if self.device[:2] == "hd":
				return readFile('/proc/ide/' + self.device + '/model')
			elif self.device[:2] == "sd":
				vendor = readFile(self.phys_path + '/vendor')
				model = readFile(self.phys_path + '/model')
				return vendor + '(' + model + ')'
			elif self.device.startswith('mmcblk'):
				return readFile(self.sysfsPath('device/name'))
			else:
				raise Exception("no hdX or sdX or mmcX")
		except Exception, e:
			print "[Harddisk] Failed to get model:", e
			return "-?-"

	def free(self):
		dev = self.findMount()
		if dev:
			if not os.path.exists(dev):
				os.mkdir(dev)
			stat = os.statvfs(dev)
			return int((stat.f_bfree / 1000) * (stat.f_bsize / 1000))
		return -1

	def numPartitions(self):
		numPart = -1
		if self.type == DEVTYPE_UDEV:
			try:
				devdir = os.listdir('/dev')
			except OSError:
				return -1
			for filename in devdir:
				if filename.startswith(self.device):
					numPart += 1

		elif self.type == DEVTYPE_DEVFS:
			try:
				idedir = os.listdir(self.dev_path)
			except OSError:
				return -1
			for filename in idedir:
				if filename.startswith("disc"):
					numPart += 1
				if filename.startswith("part"):
					numPart += 1
		return numPart

	def mountDevice(self):
		for parts in getProcMounts():
			if os.path.realpath(parts[0]).startswith(self.dev_path):
				self.mount_device = parts[0]
				self.mount_path = parts[1]
				self.fs_type = parts[2]
				return parts[1]

	def enumMountDevices(self):
		for parts in getProcMounts():
			if os.path.realpath(parts[0]).startswith(self.dev_path):
				yield parts[1]

	def findMount(self):
		if self.mount_path is None:
			return self.mountDevice()
		return self.mount_path

	def getFsUserFriendlyType(self):
		return Partition.getFsUserFriendlyType(self.fs_type)

	def unmount(self):
		dev = self.mountDevice()
		if dev is None:
			# not mounted, return OK
			return 0
		cmd = 'umount ' + dev
		print "[Harddisk]", cmd
		res = os.system(cmd)
		return res >> 8

	def createPartition(self):
		cmd = 'printf "8,\n;0,0\n;0,0\n;0,0\ny\n" | sfdisk -f -uS ' + self.disk_path
		res = os.system(cmd)
		return res >> 8

	def mkfs(self):
		# No longer supported, use createInitializeJob instead
		return 1

	def mount(self):
		# try mounting through fstab first
		if self.mount_device is None:
			dev = self.partitionPath("1")
		else:
			# if previously mounted, use the same spot
			dev = self.mount_device
		try:
			fstab = open("/etc/fstab")
			lines = fstab.readlines()
			fstab.close()
		except IOError:
			return -1
		for line in lines:
			parts = line.strip().split(" ")
			fspath = os.path.realpath(parts[0])
			if fspath == dev:
				print "[Harddisk] mounting:", fspath
				cmd = "mount -t auto " + fspath
				res = os.system(cmd)
				return res >> 8
		# device is not in fstab
		res = -1
		if self.type == DEVTYPE_UDEV:
			# we can let udev do the job, re-read the partition table
			res = os.system('hdparm -z ' + self.disk_path)
			# give udev some time to make the mount, which it will do asynchronously
			from time import sleep
			sleep(3)
		return res >> 8

	def fsck(self):
		# No longer supported, use createCheckJob instead
		return 1

	def killPartitionTable(self):
		zero = 512 * '\0'
		h = open(self.dev_path, 'wb')
		# delete first 9 sectors, which will likely kill the first partition too
		for i in range(9):
			h.write(zero)
		h.close()

	def killPartition(self, n):
		zero = 512 * '\0'
		part = self.partitionPath(n)
		h = open(part, 'wb')
		for i in range(3):
			h.write(zero)
		h.close()

	def createInitializeJob(self):
		job = Task.Job(_("Initializing storage device..."))
		size = self.diskSize()
		print "[Harddisk] size: %s MB" % size

		task = UnmountTask(job, self)

		task = Task.PythonTask(job, _("Removing partition table"))
		task.work = self.killPartitionTable
		task.weighting = 1

		task = Task.LoggingTask(job, _("Rereading partition table"))
		task.weighting = 1
		task.setTool('hdparm')
		task.args.append('-z')
		task.args.append(self.disk_path)

		task = Task.ConditionTask(job, _("Waiting for partition"), timeoutCount=20)
		task.check = lambda: not os.path.exists(self.partitionPath("1"))
		task.weighting = 1

		if os.path.exists('/usr/sbin/parted'):
			use_parted = True
		else:
			if size > 2097151:
				addInstallTask(job, 'parted')
				use_parted = True
			else:
				use_parted = False

		task = Task.LoggingTask(job, _("Creating partition"))
		task.weighting = 5
		if use_parted:
			task.setTool('parted')
			if size < 1024:
				# On very small devices, align to block only
				alignment = 'min'
			else:
				# Prefer optimal alignment for performance
				alignment = 'opt'
			task.args += ['-a', alignment, '-s', self.disk_path, 'mklabel', 'gpt', 'mkpart', 'primary', '0%', '100%']
		else:
			task.setTool('sfdisk')
			task.args.append('-f')
			task.args.append('-uS')
			task.args.append(self.disk_path)
			if size > 128000:
				# Start at sector 8 to better support 4k aligned disks
				print "[Harddisk] Detected >128GB disk, using 4k alignment"
				task.initial_input = "8,\n;0,0\n;0,0\n;0,0\ny\n"
			else:
				# Smaller disks (CF cards, sticks etc) don't need that
				task.initial_input = "0,\n;\n;\n;\ny\n"

		task = Task.ConditionTask(job, _("Waiting for partition"))
		task.check = lambda: os.path.exists(self.partitionPath("1"))
		task.weighting = 1

		task = MkfsTask(job, _("Creating file system"))
		big_o_options = ["dir_index", "filetype"]
		if isFileSystemSupported("ext4"):
			task.setTool("mkfs.ext4")
			big_o_options += ["extent", "flex_bg", "uninit_bg"]
		else:
			task.setTool("mkfs.ext3")
		if size > 250000:
			# No more than 256k i-nodes (prevent problems with fsck memory requirements)
			task.args += ["-T", "largefile", "-N", "262144"]
			big_o_options.append("sparse_super")
		elif size > 16384:
			# between 16GB and 250GB: 1 i-node per megabyte
			task.args += ["-T", "largefile"]
			big_o_options.append("sparse_super")
		elif size > 2048:
			# Over 2GB: 32 i-nodes per megabyte
			task.args += ["-T", "largefile", "-N", str(size * 32)]
		task.args += ["-F", "-F", "-L", getMachineName(), "-m0", "-O", ",".join(big_o_options), self.partitionPath("1")]

		task = MountTask(job, self)
		task.weighting = 3

		task = Task.ConditionTask(job, _("Waiting for mount"), timeoutCount=20)
		task.check = self.mountDevice
		task.weighting = 1

		return job

	def checkIsSupported(self):
		if self.fs_type in self.fsckOpts:
			prog = self.fsckOpts[self.fs_type][0]
			for path_dir in os.environ["PATH"].split(":"):
				if os.access(os.path.join(path_dir, prog), os.X_OK):
					return True
		return False

	def initialize(self):
		# no longer supported
		return -5

	def check(self):
		# no longer supported
		return -5

	def createCheckJob(self):
		job = Task.Job(_("Checking file system..."))
		if self.findMount():
			# Create unmount task if it was not mounted
			UnmountTask(job, self)
			dev = self.mount_device
		else:
			# otherwise, assume there is one partition
			dev = self.partitionPath("1")
		if self.fs_type not in self.fsckOpts:
			return None
		task = Task.LoggingTask(job, "fsck")
		fsckCmd = self.fsckOpts[self.fs_type]
		task.setTool(fsckCmd[0])

		# fsck.ext? return codes less than 4 are not real errors
		class FsckReturncodePostCondition(Task.ReturncodePostcondition):
			def check(self, task):
				return task.returncode < 4

		task.postconditions = [FsckReturncodePostCondition()]
		task.args += fsckCmd[1:] + (dev, )
		MountTask(job, self)
		task = Task.ConditionTask(job, _("Waiting for mount"))
		task.check = self.mountDevice
		return job

	def createExt4ConversionJob(self):
		if not isFileSystemSupported('ext4'):
			raise Exception(_("Your system does not support ext4"))
		job = Task.Job(_("Converting ext3 to ext4..."))
		if not os.path.exists('/sbin/tune2fs'):
			addInstallTask(job, 'e2fsprogs-tune2fs')
		if self.findMount():
			# Create unmount task if it was not mounted
			UnmountTask(job, self)
			dev = self.mount_device
		else:
			# otherwise, assume there is one partition
			dev = self.partitionPath("1")
		task = Task.LoggingTask(job, "fsck")
		task.setTool('fsck.ext3')
		task.args.append('-p')
		task.args.append(dev)
		task = Task.LoggingTask(job, "tune2fs")
		task.setTool('tune2fs')
		task.args.append('-O')
		task.args.append('extent,flex_bg,uninit_bg,dir_index,filetype')
		task.args.append('-o')
		task.args.append('journal_data_writeback')
		task.args.append(dev)
		task = Task.LoggingTask(job, "fsck")
		task.setTool('fsck.ext4')
		task.postconditions = []  # ignore result, it will always "fail"
		task.args.append('-f')
		task.args.append('-p')
		task.args.append('-D')
		task.args.append(dev)
		MountTask(job, self)
		task = Task.ConditionTask(job, _("Waiting for mount"))
		task.check = self.mountDevice
		return job

	def getDeviceDir(self):
		return self.dev_path

	def getDeviceName(self):
		return self.disk_path

	def getDevicePhysicalName(self):
		return self.phys_path

	# the HDD idle poll daemon.
	# as some harddrives have a buggy standby timer, we are doing this by hand here.
	# first, we disable the hardware timer. then, we check every now and then if
	# any access has been made to the disc. If there has been no access over a specifed time,
	# we set the hdd into standby.
	def readStats(self):
		if os.path.exists("/sys/block/%s/stat" % self.device):
			f = open("/sys/block/%s/stat" % self.device)
			l = f.read()
			f.close()
			data = l.split(None, 5)
			return int(data[0]), int(data[4])
		else:
			return -1, -1

	def startIdle(self):
		from enigma import eTimer

		# disable HDD standby timer
		if self.bus() == _("External"):
			Console().ePopen(("sdparm", "sdparm", "--set=SCT=0", self.disk_path))
		else:
			Console().ePopen(("hdparm", "hdparm", "-S0", self.disk_path))
		self.timer = eTimer()
		self.timer.callback.append(self.runIdle)
		self.idle_running = True
		self.setIdleTime(self.max_idle_time)  # kick the idle polling loop

	def runIdle(self):
		if not self.max_idle_time:
			return
		t = time.time()

		idle_time = t - self.last_access

		stats = self.readStats()
		l = sum(stats)

		if l != self.last_stat and l >= 0:  # access
			self.last_stat = l
			self.last_access = t
			idle_time = 0
			self.is_sleeping = False

		if idle_time >= self.max_idle_time and not self.is_sleeping:
			self.setSleep()
			self.is_sleeping = True

	def setSleep(self):
		if self.bus() == _("External"):
			Console().ePopen(("sdparm", "sdparm", "--flexible", "--readonly", "--command=stop", self.disk_path))
		else:
			Console().ePopen(("hdparm", "hdparm", "-y", self.disk_path))

	def setIdleTime(self, idle):
		self.max_idle_time = idle
		if self.idle_running:
			if not idle:
				self.timer.stop()
			else:
				self.timer.start(idle * 100, False)  # poll 10 times per period.

	def isSleeping(self):
		return self.is_sleeping

class Partition:

	fsUserFriendlyTypes = {
		"exfat": _("exFAT"),
		"hfs": _("HFS"),
		"hfsplus": _("HFS+"),
		"iso9660": _("ISO9660"),
		"msdos": _("FAT"),
		"ntfs": _("NTFS"),
		"squashfs": _("Squashfs"),
		"ubifs": _("UBIFS"),
		"udf": _("UDF"),
		"vfat": _("FAT"),
		"yaffs": _("YAFFS1"),
		"yaffs2": _("YAFFS2"),
	}

	# for backward compatibility, force_mounted actually means "hotplug"
	def __init__(self, mountpoint, device=None, description="", shortdescription="", force_mounted=False):
		self.mountpoint = mountpoint
		self.description = description
		if not shortdescription:
			shortdescription = description
		self.shortdescription = shortdescription
		self.force_mounted = mountpoint and force_mounted
		self.is_hotplug = force_mounted  # so far; this might change.
		self.device = device

	def __str__(self):
		return "Partition(mountpoint=%s, description=%s ,shortdescription=%s, device=%s)" % (self.mountpoint, self.description, self.shortdescription, self.device)

	def stat(self):
		if self.mountpoint:
			return os.statvfs(self.mountpoint)
		else:
			raise OSError("Device %s is not mounted" % self.device)

	def free(self):
		try:
			s = self.stat()
			return s.f_bavail * s.f_bsize
		except OSError:
			return None

	def total(self):
		try:
			s = self.stat()
			return s.f_blocks * s.f_bsize
		except OSError:
			return None

	def tabbedDescription(self):
		if self.mountpoint.startswith('/media/net') or self.mountpoint.startswith('/media/autofs'):
			# Network devices have a user defined name
			return self.description
		return self.description + '\t' + self.mountpoint

	def tabbedShortDescription(self):
		if self.mountpoint.startswith('/media/net') or self.mountpoint.startswith('/media/autofs'):
			# Network devices have a user defined name
			return self.shortdescription
		return self.shortdescription + '\t' + self.mountpoint

	@staticmethod
	def getFsUserFriendlyType(fs_type):
		return Partition.fsUserFriendlyTypes.get(fs_type, fs_type or "Unknown")

	def mounted(self, mounts=None):
		# THANK YOU PYTHON FOR STRIPPING AWAY f_fsid.
		# TODO: can os.path.ismount be used?
		if self.force_mounted:
			return True
		if self.mountpoint:
			if mounts is None:
				mounts = getProcMounts()
			for parts in mounts:
				if self.mountpoint.startswith(parts[1]):  # use startswith so a mount not ending with '/' is also detected.
					return True
		return False

	def filesystem(self, mounts=None):
		if self.mountpoint:
			if mounts is None:
				mounts = getProcMounts()
			for fields in mounts:
				if self.mountpoint.endswith('/') and not self.mountpoint == '/':
					if fields[1] + '/' == self.mountpoint:
						return fields[2]
				else:
					if fields[1] == self.mountpoint:
						return fields[2]
		return ''

DEVICEDB = {
	# Indexed on About.getModelString()
	"ini-t2":
	{
		# USB-1
		"/devices/platform/ohci-brcm.0/usb2/2-2/": "Front USB Slot",
		"/devices/platform/ohci-brcm.0/usb2/2-1/": "Back USB Slot",
		# USB-2
		"/devices/platform/ehci-brcm.0/usb1/1-2/": "Front USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-1/": "Back USB Slot",
		"/devices/platform/strict-ahci.0/ata1/": "Internal HDD",
	},
	"ini-7012au":
	{
		# USB-1
		"/devices/platform/ohci-brcm.1/usb4/4-1/": "Front USB Slot",
		"/devices/platform/ohci-brcm.0/usb3/3-2/": "Back, upper USB Slot",
		"/devices/platform/ohci-brcm.0/usb3/3-1/": "Back, lower USB Slot",
		# USB-2
		"/devices/platform/ehci-brcm.1/usb2/2-1/": "Front USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-2/": "Back, upper USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-1/": "Back, lower USB Slot",
		"/devices/pci0000:01/0000:01:00.0/ata1/": "Internal HDD",
		"/devices/pci0000:01/0000:01:00.0/ata2/": "eSATA HDD",
	},
	"ini-8000au":
	{
		# USB-1
		"/devices/platform/ohci-brcm.2/usb7/7-1/": "Front USB Slot",
		"/devices/platform/ohci-brcm.1/usb6/6-1/": "Back, upper USB Slot",
		"/devices/platform/ohci-brcm.0/usb5/5-1/": "Back, lower USB Slot",
		# USB-2
		"/devices/platform/ehci-brcm.2/usb3/3-1/": "Front USB Slot",
		"/devices/platform/ehci-brcm.1/usb2/2-1/": "Back, upper USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-1/": "Back, lower USB Slot",
		"/devices/platform/strict-ahci.0/ata1/": "Internal HDD",
		"/devices/platform/strict-ahci.0/ata2/": "eSATA HDD",
	},
	# Indexed on HardwareInfo().device_name
	"dm8000":
	{
		# dm8000:
		"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.1/1-1.1:1.0": "Front USB Slot",
		"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.2/1-1.2:1.0": "Back, upper USB Slot",
		"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.3/1-1.3:1.0": "Back, lower USB Slot",
		"/devices/platform/brcm-ehci-1.1/usb2/2-1/2-1:1.0/host1/target1:0:0/1:0:0:0": "DVD Drive",
	},
	"dm800":
	{
		# dm800:
		"/devices/platform/brcm-ehci.0/usb1/1-2/1-2:1.0": "Upper USB Slot",
		"/devices/platform/brcm-ehci.0/usb1/1-1/1-1:1.0": "Lower USB Slot",
	},
	"dm800se":
	{
		# USB-1
		"/devices/platform/ohci-brcm.1/usb4/4-1/": "Front USB Slot",
		"/devices/platform/ohci-brcm.0/usb3/3-2/": "Back, upper USB Slot",
		"/devices/platform/ohci-brcm.0/usb3/3-1/": "Back, lower USB Slot",
		# USB-2
		"/devices/platform/ehci-brcm.1/usb2/2-1/": "Front USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-2/": "Back, upper USB Slot",
		"/devices/platform/ehci-brcm.0/usb1/1-1/": "Back, lower USB Slot",
		"/devices/pci0000:01/0000:01:00.0/ata1/": "Internal HDD",
		"/devices/pci0000:01/0000:01:00.0/ata2/": "eSATA HDD",
	},
	"dm7025":
	{
		# dm7025:
		"/devices/pci0000:00/0000:00:14.1/ide1/1.0": "CF Card Slot",  # hdc
		"/devices/pci0000:00/0000:00:14.1/ide0/0.0": "Internal HDD",
	},
	"beyonwizu4":
	{
		"/devices/platform/rdb/f045a000.sata/ata1": "Internal HDD",
		"/devices/platform/rdb/f0471000.xhci_v2/usb2/2-1/": "Back USB3 Slot", # With USB-3 device
		"/devices/platform/rdb/f0470300.ehci_v2/usb3/3-1/": "Back USB3 Slot", # With USB-2 device
		"/devices/platform/rdb/f0470400.ohci_v2/usb5/5-1/": "Back USB3 Slot", # With USB-1 device
		"/devices/platform/rdb/f0470500.ehci_v2/usb4/4-1/4-1.3/": "Back, upper USB2 Slot", # With USB-2 or USB-1 device
		"/devices/platform/rdb/f0470500.ehci_v2/usb4/4-1/4-1.4/": "Back, lower USB2 Slot", # With USB-2 or USB-1 device
		"/devices/platform/rdb/f0470500.ehci_v2/usb4/4-1/4-1.1/": "Front USB2 Slot", # With USB-2 or USB-1 device
	},
	"beyonwizv2":
	{
		"/devices/platform/soc/f98a0000.xhci/usb4/4-1/": "Back USB3 Slot", # With USB-3 device
		"/devices/platform/soc/f98a0000.xhci/usb3/3-1/": "Back USB3 Slot", # With USB-2 or USB-1 device
		"/devices/platform/soc/f9890000.ehci/usb1/1-1/1-1.2/": "Back USB2 Slot", # With USB-2 or USB-1 device
		"/devices/platform/soc/f9890000.ehci/usb1/1-1/1-1.3": "Back SD Slot",
	},
}

def addInstallTask(job, package):
	task = Task.LoggingTask(job, "update packages")
	task.setTool('opkg')
	task.args.append('update')
	task = Task.LoggingTask(job, "Install " + package)
	task.setTool('opkg')
	task.args.append('install')
	task.args.append(package)

class VolumeLabels:
	def __init__(self):
		self.stale = True
		self.volume_labels = {}

	def fetchVolumeLabels(self):
		import subprocess
		self.volume_labels = {}
		lines = []
		try:
			lines = subprocess.check_output(["blkid", "-s", "LABEL"]).split("\n")
		except Exception, e:
			print "[HarddiskManager] fetchVolumeLabels", str(e)

		for l in lines:
			if l:
				l = l.strip()
				l = l.replace('"', "")
				l = l.replace("LABEL=", "").replace("/dev/", "")
				d = l.split(None, 1)
				if len(d) == 2:
					if d[0][-1] == ':':
						d[0] = d[0][:-1]
					self.volume_labels[d[0]] = d[1]
		print "[Harddisk] volume labels:", self.volume_labels
		self.stale = False

	def getVolumeLabel(self, device):
		if self.stale:
			self.fetchVolumeLabels()

		if device in self.volume_labels:
			return self.volume_labels[device]

		return None

	def makeStale(self):
		self.stale = True

class HarddiskManager:
	def __init__(self):
		self.hdd = []
		self.cd = ""
		# Partitions should always have a trailing /
		self.partitions = []
		self.volume_labels = VolumeLabels()
		self.devices_scanned_on_init = []
		self.on_partition_list_change = CList()
		self.enumerateBlockDevices()
		# Find stuff not detected by the enumeration
		self.enumerateNetworkMounts()
		# Find stuff not detected by the enumeration
		p = [("/", _("Internal Flash")), ("/media/upnp/", _("DLNA")), ]

		self.partitions.extend([Partition(mountpoint=x[0], description=x[1], shortdescription=x[1]) for x in p])

	def getBlockDevInfo(self, blockdev):
		devpath = "/sys/block/" + blockdev
		error = False
		removable = False
		BLACKLIST=[]
		if getMachineBuild() in ('gbmv200','multibox','h9combo','v8plus','hd60','hd61','vuduo4k','ustym4kpro','beyonwizv2','dags72604','u51','u52','u53','u54','u5','u5pvr','cc1','sf8008','vuzero4k','et1x000','vuuno4k','vuuno4kse','vuultimo4k','vusolo4k','hd51','hd52','sf4008','dm900','dm7080','dm820', 'gb7252', 'dags7252', 'vs1500','h7','8100s','et13000','sf5008'):
			BLACKLIST=["mmcblk0"]
		elif getMachineBuild() in ('xc7439','osmio4k'):
			BLACKLIST=["mmcblk1"]

		blacklisted = False
		if blockdev[:7] in BLACKLIST:
			blacklisted = True
		if blockdev.startswith("mmcblk") and (re.search(r"mmcblk\dboot", blockdev) or re.search(r"mmcblk\drpmb", blockdev)):
			blacklisted = True
		is_cdrom = False
		partitions = []
		try:
			if os.path.exists(devpath + "/removable"):
				removable = bool(int(readFile(devpath + "/removable")))
			if os.path.exists(devpath + "/dev"):
				dev = int(readFile(devpath + "/dev").split(':')[0])
			else:
				dev = None
			devlist = [1, 7, 31, 253, 254] # ram, loop, mtdblock, romblock, ramzswap
			if dev in devlist:
				blacklisted = True
			if blockdev[0:2] == 'sr':
				is_cdrom = True
			if blockdev[0:2] == 'hd':
				try:
					media = readFile("/proc/ide/%s/media" % blockdev)
					if "cdrom" in media:
						is_cdrom = True
				except IOError:
					error = True
			# check for partitions
			if not is_cdrom and os.path.exists(devpath):
				for partition in os.listdir(devpath):
					if partition[0:len(blockdev)] != blockdev:
						continue
					if dev == 179 and not re.search(r"mmcblk\dp\d+", partition):
						continue
					partitions.append(partition)
			else:
				self.cd = blockdev
		except IOError:
			error = True
		# check for medium
		medium_found = True
		try:
			if os.path.exists("/dev/" + blockdev):
				open("/dev/" + blockdev).close()
		except IOError, err:
			if err.errno == 159:  # no medium present
				medium_found = False

		return error, blacklisted, removable, is_cdrom, partitions, medium_found

	def enumerateBlockDevices(self):
		print "[Harddisk] enumerating block devices..."
		self.volume_labels.makeStale()
		for blockdev in os.listdir("/sys/block"):
			error, blacklisted, removable, is_cdrom, partitions, medium_found = self.addHotplugPartition(blockdev, makestale=False)
			if not error and not blacklisted and medium_found:
				for part in partitions:
					self.addHotplugPartition(part, makestale=False)
				self.devices_scanned_on_init.append((blockdev, removable, is_cdrom, medium_found))

	def enumerateNetworkMounts(self):
		print "[Harddisk] enumerating network mounts..."
		netmount = (os.path.exists('/media/net') and os.listdir('/media/net')) or ""
		if len(netmount) > 0:
			for fil in netmount:
				if os.path.ismount('/media/net/' + fil):
					print "[Harddisk] new Network Mount", fil, '->', os.path.join('/media/net/', fil)
					self.partitions.append(Partition(mountpoint=os.path.join('/media/net/', fil + '/'), description=fil, shortdescription=fil))
		autofsmount = (os.path.exists('/media/autofs') and os.listdir('/media/autofs')) or ""
		if len(autofsmount) > 0:
			for fil in autofsmount:
				if os.path.ismount('/media/autofs/' + fil) or os.path.exists('/media/autofs/' + fil):
					print "[Harddisk] new Network Mount", fil, '->', os.path.join('/media/autofs/', fil)
					self.partitions.append(Partition(mountpoint=os.path.join('/media/autofs/', fil + '/'), description=fil, shortdescription=fil))
		if os.path.ismount('/media/hdd') and '/media/hdd/' not in [p.mountpoint for p in self.partitions]:
			print "[Harddisk] new Network Mount being used as HDD replacement -> /media/hdd/"
			self.partitions.append(Partition(mountpoint='/media/hdd/', description='/media/hdd', shortdescription='/media/hdd'))

	def getAutofsMountpoint(self, device):
		r = self.getMountpoint(device)
		if r is None:
			return "/media/" + device
		return r

	def getMountpoint(self, device):
		dev = "/dev/%s" % device
		for item in getProcMounts():
			if item[0] == dev:
				return item[1] + '/'
		return None

	def addHotplugPartition(self, device, physdev=None, makestale=True):
		# device is the device name, without /dev
		# physdev is the physical device path, which we (might) use to determine the userfriendly name
		if not physdev:
			dev, part = self.splitDeviceName(device)
			try:
				physdev = os.path.realpath('/sys/block/' + dev + '/device')[4:]
			except OSError:
				physdev = dev
				print "[Harddisk] couldn't determine blockdev physdev for device", device
		else:
			physdev = os.path.realpath('/sys' + physdev)[4:]

		error, blacklisted, removable, is_cdrom, partitions, medium_found = self.getBlockDevInfo(self.splitDeviceName(device)[0])
		if not blacklisted and medium_found:
			if makestale:
				self.volume_labels.makeStale()
			(description, shortdescription) = self._getUserfriendlyDeviceName(device, physdev)
			p = Partition(mountpoint=self.getMountpoint(device), description=description, shortdescription=shortdescription, force_mounted=True, device=device)
			self.partitions.append(p)
			if p.mountpoint:  # Plugins won't expect unmounted devices
				self.on_partition_list_change("add", p)
			# see if this is a harddrive
			l = len(device)
			if l and (not device[l - 1].isdigit() or (device.startswith('mmcblk') and not re.search(r"mmcblk\dp\d+", device))):
				self.hdd.append(Harddisk(device, removable))
				self.hdd.sort()
				SystemInfo["Harddisk"] = True
		return error, blacklisted, removable, is_cdrom, partitions, medium_found

	def addHotplugAudiocd(self, device, physdev = None):
		# device is the device name, without /dev
		# physdev is the physical device path, which we (might) use to determine the userfriendly name
		if not physdev:
			dev, part = self.splitDeviceName(device)
			try:
				physdev = os.path.realpath('/sys/block/' + dev + '/device')[4:]
			except OSError:
				physdev = dev
				print "couldn't determine blockdev physdev for device", device
		error, blacklisted, removable, is_cdrom, partitions, medium_found = self.getBlockDevInfo(device)
		if not blacklisted and medium_found:
			description = self.getUserfriendlyDeviceName(device, physdev)
			p = Partition(mountpoint = "/media/audiocd", description = description, force_mounted = True, device = device)
			self.partitions.append(p)
			self.on_partition_list_change("add", p)
			SystemInfo["Harddisk"] = False
		return error, blacklisted, removable, is_cdrom, partitions, medium_found

	def removeHotplugPartition(self, device):
		for x in self.partitions[:]:
			if x.device == device:
				self.partitions.remove(x)
				if x.mountpoint:  # Plugins won't expect unmounted devices
					self.on_partition_list_change("remove", x)
		l = len(device)
		if l and (not device[l - 1].isdigit() or (device.startswith('mmcblk') and not re.search(r"mmcblk\dp\d+", device))):
			for hdd in self.hdd:
				if hdd.device == device:
					hdd.stop()
					self.hdd.remove(hdd)
					break
			SystemInfo["Harddisk"] = len(self.hdd) > 0

	def HDDCount(self):
		return len(self.hdd)

	def HDDList(self):
		list = []
		for hd in self.hdd:
			try:
				hdd = self.getUserfriendlyDeviceName(hd.disk_path, os.path.realpath(hd.phys_path))
			except Exception as ex:
				print "[Harddisk] couldn't get friendly name for %s: %s" % (hd.phys_path, ex)
				hdd = hd.model() + " - " + hd.bus()
			cap = hd.capacity()
			if cap != "":
				hdd += " (" + cap + ")"
			list.append((hdd, hd))
		return list

	def getCD(self):
		return self.cd

	def getMountedPartitions(self, onlyhotplug=False, mounts=None):
		if mounts is None:
			mounts = getProcMounts()
		parts = [x for x in self.partitions if (x.is_hotplug or not onlyhotplug) and x.mounted(mounts)]
		devs = set([x.device for x in parts])
		for devname in devs.copy():
			if not devname:
				continue
			dev, part = self.splitDeviceName(devname)
			if part and dev in devs:  # if this is a partition and we still have the wholedisk, remove wholedisk
				devs.remove(dev)

		# return all devices which are not removed due to being a wholedisk when a partition exists
		return [x for x in parts if not x.device or x.device in devs]

	def splitDeviceName(self, devname):
		if re.search(r"^mmcblk\d(?:p\d+$|$)", devname):
			m = re.search(r"(?P<dev>mmcblk\d)p(?P<part>\d+)$", devname)
			if m:
				return m.group('dev'), m.group('part') and int(m.group('part')) or 0
			else:
				return devname, 0
		else:
			# this works for: sdaX, hdaX, sr0 (which is in fact dev="sr0", part=""). It doesn't work for other names like mtdblock3, but they are blacklisted anyway.
			dev = devname[:3]
			part = devname[3:]
			for p in part:
				if (not p.isdigit()) or dev == "ram":
					return devname, 0
			return dev, part and int(part) or 0

	def getPhysicalDeviceLocation(self, phys):
		from Tools.HardwareInfo import HardwareInfo
		if phys.startswith("/sys"):
			phys = phys[4:]
		for physdevprefix, pdescription in (DEVICEDB.get(getModelString(), {}) or DEVICEDB.get(HardwareInfo().device_name, {})).items():
			if phys.startswith(physdevprefix):
				return pdescription
		return None

	def _getUserfriendlyDeviceName(self, device, phys):
		dev, part = self.splitDeviceName(device)
		if phys.startswith("/sys"):
			phys = phys[4:]
		shortdescription = description = "External Storage %s" % dev
		volume_label = self.volume_labels.getVolumeLabel(device)
		if volume_label:
			shortdescription = description = volume_label
		if not volume_label:
			try:
				description = readFile("/sys" + phys + "/model")
			except IOError, s:
				print "[Harddisk] couldn't read %s: %s" % ("/sys" + phys + "/model", s)
		pdescription = self.getPhysicalDeviceLocation(phys)
		if pdescription is not None:
			if volume_label:
				description = "%s (%s)" % (description, pdescription)
			else:
				description = "%s (%s)" % (pdescription, description)
				shortdescription = pdescription
		# not wholedisk and not partition 1
		if not volume_label and part and part != 1:
			description += _(" (Partition %d)") % part
		return (description, shortdescription)

	def getUserfriendlyDeviceName(self, device, phys):
		return self._getUserfriendlyDeviceName(device, phys)[0]

	def getUserfriendlyDeviceShortName(self, device, phys):
		return self._getUserfriendlyDeviceName(device, phys)[1]

	def addMountedPartition(self, device, desc):
		# Ensure we have a trailing /
		if device and device[-1] != "/":
			device += "/"
		for x in self.partitions:
			if x.mountpoint == device:
				# already_mounted
				return
		self.partitions.append(Partition(mountpoint=device, description=desc, shortdescription=desc))

	def removeMountedPartition(self, mountpoint):
		if mountpoint and mountpoint[-1] != "/":
			mountpoint += "/"
		for x in self.partitions[:]:
			if x.mountpoint == mountpoint:
				self.partitions.remove(x)
				self.on_partition_list_change("remove", x)

	def setDVDSpeed(self, device, speed=0):
		ioctl_flag = int(0x5322)
		if not device.startswith('/'):
			device = "/dev/" + device
		try:
			from fcntl import ioctl
			cd = open(device)
			ioctl(cd.fileno(), ioctl_flag, speed)
			cd.close()
		except Exception, ex:
			print "[Harddisk] Failed to set %s speed to %s" % (device, speed), ex

class UnmountTask(Task.LoggingTask):
	def __init__(self, job, hdd):
		Task.LoggingTask.__init__(self, job, _("Unmount"))
		self.hdd = hdd
		self.mountpoints = []

	def prepare(self):
		try:
			dev = self.hdd.disk_path.split('/')[-1]
			open('/dev/nomount.%s' % dev, "wb").close()
		except Exception, e:
			print "[Harddisk] Failed to create /dev/nomount.%s:" % dev, e
		self.setTool('umount')
		self.args.append('-f')
		for dev in self.hdd.enumMountDevices():
			self.args.append(dev)
			self.postconditions.append(Task.ReturncodePostcondition())
			self.mountpoints.append(dev)
		if not self.mountpoints:
			print "[Harddisk] UnmountTask: No mountpoints found?"
			self.cmd = 'true'
			self.args = [self.cmd]

	def afterRun(self):
		for path in self.mountpoints:
			try:
				os.rmdir(path)
			except Exception, ex:
				print "[Harddisk] Failed to remove path '%s':" % path, ex

class MountTask(Task.LoggingTask):
	def __init__(self, job, hdd):
		Task.LoggingTask.__init__(self, job, _("Mount"))
		self.hdd = hdd

	def prepare(self):
		try:
			dev = self.hdd.disk_path.split('/')[-1]
			os.unlink('/dev/nomount.%s' % dev)
		except Exception, e:
			print "[Harddisk] Failed to remove /dev/nomount.%s:" % dev, e
		# try mounting through fstab first
		if self.hdd.mount_device is None:
			dev = self.hdd.partitionPath("1")
		else:
			# if previously mounted, use the same spot
			dev = self.hdd.mount_device
		fstab = open("/etc/fstab")
		lines = fstab.readlines()
		fstab.close()
		for line in lines:
			parts = line.strip().split(" ")
			fspath = os.path.realpath(parts[0])
			if os.path.realpath(fspath) == dev:
				self.setCmdline("mount -t auto " + fspath)
				self.postconditions.append(Task.ReturncodePostcondition())
				return
		# device is not in fstab
		if self.hdd.type == DEVTYPE_UDEV:
			# we can let udev do the job, re-read the partition table
			# Sorry for the sleep 2 hack...
			self.setCmdline('sleep 2; hdparm -z ' + self.hdd.disk_path)
			self.postconditions.append(Task.ReturncodePostcondition())


class MkfsTask(Task.LoggingTask):
	def prepare(self):
		self.fsck_state = None

	def processOutput(self, data):
		print "[Harddisk] mkfs", data
		if 'Writing inode tables:' in data:
			self.fsck_state = 'inode'
		elif 'Creating journal' in data:
			self.fsck_state = 'journal'
			self.setProgress(80)
		elif 'Writing superblocks ' in data:
			self.setProgress(95)
		elif self.fsck_state == 'inode':
			if '/' in data:
				try:
					d = data.strip(' \x08\r\n').split('/', 1)
					if '\x08' in d[1]:
						d[1] = d[1].split('\x08', 1)[0]
					self.setProgress(80 * int(d[0]) / int(d[1]))
				except Exception, e:
					print "[Harddisk] mkfs E:", e
				return  # don't log the progess
		self.log.append(data)


def internalHDDNotSleeping():
	if harddiskmanager.HDDCount():
		for hdd in harddiskmanager.HDDList():
			if ("pci" in hdd[1].phys_path or "ahci" in hdd[1].phys_path) and hdd[1].max_idle_time and not hdd[1].isSleeping():
				return True
	return False

harddiskmanager = HarddiskManager()
SystemInfo["ext4"] = isFileSystemSupported("ext4")
