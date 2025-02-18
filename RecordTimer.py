from boxbranding import getMachineBrand, getMachineName
import xml.etree.cElementTree
from time import localtime, strftime, ctime, time
from bisect import insort
from sys import maxint
import os
from enigma import eEPGCache, getBestPlayableServiceReference, eServiceReferenceDVB, eServiceReference, eServiceCenter, iRecordableService, quitMainloop, eActionMap, setPreferredTuner, eStreamServer

from Components.config import config
from Components import Harddisk
from Components.UsageConfig import defaultMoviePath
from Components.SystemInfo import SystemInfo
from Components.TimerSanityCheck import TimerSanityCheck
from Screens.MessageBox import MessageBox
import Screens.Standby
import Screens.InfoBar
from Tools.ServiceReference import service_types_tv_ref, serviceRefAppendPath
from Tools import Directories, Notifications, ASCIItranslit, Trashcan
from Tools.XMLTools import stringToXML
import timer
import NavigationInstance
from ServiceReference import ServiceReference
import subprocess, threading


# In descriptions etc. we have:
# service reference	(to get the service name)
# name			(title)
# description		(description)
# event data		(ONLY for time adjustments etc.)


# Parses an event, and returns a (begin, end, name, duration, eit)-tuple.
# begin and end will be adjusted by the margin before/after recording start/end
def parseEvent(ev, description=True):
	if description:
		name = ev.getEventName()
		description = ev.getShortDescription()
		if description == "":
			description = ev.getExtendedDescription()
	else:
		name = ""
		description = ""
	begin = ev.getBeginTime()
	end = begin + ev.getDuration()
	eit = ev.getEventId()
	begin -= config.recording.margin_before.value * 60
	end += config.recording.margin_after.value * 60
	return begin, end, name, description, eit

class AFTEREVENT:
	def __init__(self):
		pass

	NONE = 0
	STANDBY = 1
	DEEPSTANDBY = 2
	AUTO = 3

def findSafeRecordPath(dirname):
	if not dirname:
		return None
	dirname = os.path.realpath(dirname)
	mountpoint = Harddisk.findMountPoint(dirname)
	if not os.path.ismount(mountpoint):
		print '[RecordTimer] media is not mounted:', dirname
		return None
	if not os.path.isdir(dirname):
		try:
			os.makedirs(dirname)
		except Exception, ex:
			print '[RecordTimer] Failed to create dir "%s":' % dirname, ex
			return None
	return dirname

# This code is for use by hardware with a stb device file which, when
# non-zero, can display a visual indication on the front-panel that
# recordings are in progress, with possibly different icons for
# different numbers of concurrent recordings.
# NOTE that Navigation.py uses symbol_signal (which the mbtwin does not
#  have) to indicate that a recording is being played back. Different.
#
# Define the list of boxes which can use the code by setting the device
# path and number of different states it supports.
# Any undefined box will not use this code.
#
SID_symbol_states = {
	"mbtwin": ('/proc/stb/lcd/symbol_circle', 4)
}
from boxbranding import getBoxType
SID_code_states = SID_symbol_states.setdefault(getBoxType(), (None, 0))

n_recordings = 0  # Must be when we start running...
def SetIconDisplay(nrec):
	if SID_code_states[0] is None:  # Not the code for us
		return
	(wdev, max_states) = SID_code_states
	if nrec == 0:                   # An absolute setting - clear it...
		f = open(wdev, 'w')
		f.write('0')
		f.close()
		return
#
	sym = nrec
	if sym > max_states:
		sym = max_states
	if sym < 0:		    # Sanity check - just in case...
		sym = 0
	f = open(wdev, 'w')
	f.write(str(sym))
	f.close()
	return

# Define a function that is called at the start and stop of all
# recordings. This allows us to track the number of actual recordings.
# Other recording-related accounting could also be added here.
# alter is 1 at a recording start, -1 at a stop and 0 as enigma2 starts
# to initialize things).


def RecordingsState(alter):
	# Since we are about to modify it we need to declare it as global
	#
	global n_recordings
	if not -1 <= alter <= 1:
		return

# Adjust the number of currently running recordings...
#
	if alter == 0:              # Initialize
		n_recordings = 0
	else:
		n_recordings += alter
	if n_recordings < 0:        # Sanity check - just in case...
		n_recordings = 0
	SetIconDisplay(n_recordings)
	return

RecordingsState(0)       # Initialize

# type 1 = digital television service
# type 4 = nvod reference service (NYI)
# type 17 = MPEG-2 HD digital television service
# type 22 = advanced codec SD digital television
# type 24 = advanced codec SD NVOD reference service (NYI)
# type 25 = advanced codec HD digital television
# type 27 = advanced codec HD NVOD reference service (NYI)
# type 2 = digital radio sound service
# type 10 = advanced codec digital radio sound service

service_types_tv = service_types_tv_ref.toString()
wasRecTimerWakeup = False

# Please do not translate log messages
class RecordTimerEntry(timer.TimerEntry, object):
	def __init__(self, serviceref, begin, end, name, description, eit, disabled=False, justplay=False, afterEvent=AFTEREVENT.AUTO, checkOldTimers=False, dirname=None, tags=None, descramble='notset', record_ecm='notset', isAutoTimer=False, ice_timer_id=None, always_zap=False, rename_repeat=True):
		timer.TimerEntry.__init__(self, int(begin), int(end))
		if checkOldTimers:
			if self.begin < time() - 1209600:  # 2 weeks
				self.begin = int(time())

		if self.end < self.begin:
			self.end = self.begin

		if not isinstance(serviceref, ServiceReference):
			raise AssertionError("invalid serviceref")

		if serviceref and serviceref.isRecordable():
			self.service_ref = serviceref
		else:
			self.service_ref = ServiceReference(None)
		self.dontSave = False
		self.eit = None
		if not description or not name or not eit:
			evt = self.getEventFromEPGId(eit) or self.getEventFromEPG()
			if evt:
				if not description:
					description = evt.getShortDescription()
				if not description:
					description = evt.getExtendedDescription()
				if not name:
					name = evt.getEventName()
				if not eit:
					eit = evt.getEventId()
		self.eit = eit
		self.name = name
		self.description = description
		self.disabled = disabled
		self.timer = None
		self.__record_service = None
		self.start_prepare = 0
		self.justplay = justplay
		self.always_zap = always_zap
		self.afterEvent = afterEvent
		self.dirname = dirname
		self.dirnameHadToFallback = False
		self.autoincrease = False
		self.autoincreasetime = 3600 * 24  # 1 day
		self.tags = tags or []
		self.MountPath = None
		self.messageString = ""
		self.messageStringShow = False
		self.messageBoxAnswerPending = False
		self.justTriedFreeingTuner = False
		self.MountPathRetryCounter = 0
		self.MountPathErrorNumber = 0
		self.lastend = 0

		if descramble == 'notset' and record_ecm == 'notset':
			if config.recording.ecm_data.value == 'descrambled+ecm':
				self.descramble = True
				self.record_ecm = True
			elif config.recording.ecm_data.value == 'scrambled+ecm':
				self.descramble = False
				self.record_ecm = True
			elif config.recording.ecm_data.value == 'normal':
				self.descramble = True
				self.record_ecm = False
		else:
			self.descramble = descramble
			self.record_ecm = record_ecm

		self.rename_repeat = rename_repeat
		self.setAdvancedPriorityFrontend = None
		if SystemInfo["DVB-T_priority_tuner_available"] or SystemInfo["DVB-C_priority_tuner_available"] or SystemInfo["DVB-S_priority_tuner_available"] or SystemInfo["ATSC_priority_tuner_available"]:
			rec_ref = self.service_ref and self.service_ref.ref
			str_service = rec_ref and rec_ref.toString()
			if str_service and '%3a//' not in str_service and not str_service.rsplit(":", 1)[1].startswith("/"):
				type_service = rec_ref.getUnsignedData(4) >> 16
				if type_service == 0xEEEE:
					if SystemInfo["DVB-T_priority_tuner_available"] and config.usage.recording_frontend_priority_dvbt.value != "-2":
						if config.usage.recording_frontend_priority_dvbt.value != config.usage.frontend_priority.value:
							self.setAdvancedPriorityFrontend = config.usage.recording_frontend_priority_dvbt.value
					if SystemInfo["ATSC_priority_tuner_available"] and config.usage.recording_frontend_priority_atsc.value != "-2":
						if config.usage.recording_frontend_priority_atsc.value != config.usage.frontend_priority.value:
							self.setAdvancedPriorityFrontend = config.usage.recording_frontend_priority_atsc.value
				elif type_service == 0xFFFF:
					if SystemInfo["DVB-C_priority_tuner_available"] and config.usage.recording_frontend_priority_dvbc.value != "-2":
						if config.usage.recording_frontend_priority_dvbc.value != config.usage.frontend_priority.value:
							self.setAdvancedPriorityFrontend = config.usage.recording_frontend_priority_dvbc.value
					if SystemInfo["ATSC_priority_tuner_available"] and config.usage.recording_frontend_priority_atsc.value != "-2":
						if config.usage.recording_frontend_priority_atsc.value != config.usage.frontend_priority.value:
							self.setAdvancedPriorityFrontend = config.usage.recording_frontend_priority_atsc.value
				else:
					if SystemInfo["DVB-S_priority_tuner_available"] and config.usage.recording_frontend_priority_dvbs.value != "-2":
						if config.usage.recording_frontend_priority_dvbs.value != config.usage.frontend_priority.value:
							self.setAdvancedPriorityFrontend = config.usage.recording_frontend_priority_dvbs.value
		self.needChangePriorityFrontend = self.setAdvancedPriorityFrontend is not None or config.usage.recording_frontend_priority.value != "-2" and config.usage.recording_frontend_priority.value != config.usage.frontend_priority.value

		self.change_frontend = False
		self.InfoBarInstance = Screens.InfoBar.InfoBar.instance
		self.ts_dialog = None
		self.isAutoTimer = isAutoTimer
		self.ice_timer_id = ice_timer_id
		self.wasInStandby = False

		self.log_entries = []
		self.resetState()

	def __repr__(self):
		ice = ""
		if self.ice_timer_id:
			ice = ", ice_timer_id=%s" % self.ice_timer_id
		disabled = ""
		if self.disabled:
			disabled = ", Disabled"
		return "RecordTimerEntry(name=%s, begin=%s, end=%s, serviceref=%s, justplay=%s, isAutoTimer=%s%s%s)" % (self.name, ctime(self.begin), ctime(self.end), self.service_ref, self.justplay, self.isAutoTimer, ice, disabled)

	def log(self, code, msg):
		t = int(time())
		self.log_entries.append((t, code, msg))
		print "[RecordTimer]", ctime(t), msg

	def MountTest(self, dirname, cmd):
		if cmd == 'writeable':
			if not os.access(dirname, os.W_OK):
				self.stop_MountTest(None, cmd)
		elif cmd == 'freespace':
			s = os.statvfs(dirname)
			if (s.f_bavail * s.f_bsize) / 1000000 < 1024:
				self.stop_MountTest(None, cmd)

	def stop_MountTest(self, thread, cmd):
		if thread and thread.isAlive():
			print 'timeout thread : %s' %cmd
			thread._Thread__stop()

		if cmd == 'writeable':
			self.MountPathErrorNumber = 2
		elif cmd == 'freespace':
			self.MountPathErrorNumber = 3

	def freespace(self, WRITEERROR=False):
		if WRITEERROR:
			dirname = self.MountPath
			if findSafeRecordPath(dirname) is None:
				return ("mount '%s' is not available." % dirname, 1)
		else:
			self.MountPath = None
			if not self.dirname:
				dirname = findSafeRecordPath(defaultMoviePath())
			else:
				dirname = findSafeRecordPath(self.dirname)
				if dirname is None:
					dirname = findSafeRecordPath(defaultMoviePath())
					self.dirnameHadToFallback = True
			if not dirname:
				dirname = self.dirname
				if not dirname:
					dirname = defaultMoviePath() or '-'
				self.log(0, "Mount '%s' is not available." % dirname)
				self.MountPathErrorNumber = 1
				return False

		self.MountPathErrorNumber = 0
		for cmd in ('writeable', 'freespace'):
			print 'starting thread :%s' %cmd
			p = threading.Thread(target=self.MountTest, args=(dirname, cmd))
			t = threading.Timer(3, self.stop_MountTest, args=(p, cmd))
			t.start()
			p.start()
			p.join()
			t.cancel()
			if self.MountPathErrorNumber:
				print 'break - error number: %d' %self.MountPathErrorNumber
				break
			print 'finished thread :%s' %cmd

		if WRITEERROR:
			if self.MountPathErrorNumber == 2:
				return ("mount '%s' is not writeable." % dirname, 2)
			elif self.MountPathErrorNumber == 3:
				return ("mount '%s' has not enough free space to record." % dirname, 3)
			else:
				return ("unknown error.", 0)

		if self.MountPathErrorNumber == 2:
			self.log(0, "Mount '%s' is not writeable." % dirname)
			return False
		elif self.MountPathErrorNumber == 3:
			self.log(0, _("Mount '%s' has not enough free space to record.") % dirname)
			return False
		else:
			self.log(0, "Found enough free space to record")
			self.MountPathRetryCounter = 0
			self.MountPathErrorNumber = 0
			self.MountPath = dirname
			return True

	def calculateFilename(self, name=None):
		service_name = self.service_ref.getServiceName()
		begin_date = strftime("%Y%m%d %H%M", localtime(self.begin))

		name = name or self.name
		filename = begin_date + " - " + service_name
		if name:
			if config.recording.filename_composition.value == "event":
				filename = name + ' - ' + begin_date + "_" + service_name
			elif config.recording.filename_composition.value == "name":
				filename = name + ' - ' + begin_date
			elif config.recording.filename_composition.value == "short":
				filename = strftime("%Y%m%d", localtime(self.begin)) + " - " + name
			elif config.recording.filename_composition.value == "long":
				filename += " - " + name + " - " + self.description
			else:
				filename += " - " + name  # standard

		if config.recording.ascii_filenames.value:
			filename = ASCIItranslit.legacyEncode(filename)

		self.Filename = Directories.getRecordingFilename(filename, self.MountPath)
		self.log(0, "Filename calculated as: '%s'" % self.Filename)
		return self.Filename

	def getEventFromEPGId(self, id=None):
		id = id or self.eit
		epgcache = eEPGCache.getInstance()
		ref = self.service_ref and self.service_ref.ref
		return id and epgcache.lookupEventId(ref, id) or None

	def getEventFromEPG(self):
		epgcache = eEPGCache.getInstance()
		queryTime = self.begin + (self.end - self.begin) / 2
		ref = self.service_ref and self.service_ref.ref
		return epgcache.lookupEventTime(ref, queryTime)

	def tryPrepare(self):
		if self.justplay:
			return True
		else:
			if not self.calculateFilename():
				self.do_backoff()
				self.start_prepare = time() + self.backoff
				return False
			rec_ref = self.service_ref and self.service_ref.ref
			if rec_ref and rec_ref.flags & eServiceReference.isGroup:
				rec_ref = getBestPlayableServiceReference(rec_ref, eServiceReference())
				if not rec_ref:
					self.log(1, "'get best playable service for group... record' failed")
					return False

			self.setRecordingPreferredTuner()
			self.record_service = rec_ref and NavigationInstance.instance.recordService(rec_ref)

			if not self.record_service:
				self.log(1, "'record service' failed")
				self.setRecordingPreferredTuner(setdefault=True)
				return False

			name = self.name
			description = self.description
			if self.repeated:
				epgcache = eEPGCache.getInstance()
				queryTime = self.begin + (self.end - self.begin) / 2
				evt = epgcache.lookupEventTime(rec_ref, queryTime)
				if evt:
					if self.rename_repeat:
						event_description = evt.getShortDescription()
						if not event_description:
							event_description = evt.getExtendedDescription()
						if event_description and event_description != description:
							description = event_description
						event_name = evt.getEventName()
						if event_name and event_name != name:
							name = event_name
							if not self.calculateFilename(event_name):
								self.do_backoff()
								self.start_prepare = time() + self.backoff
								return False
					event_id = evt.getEventId()
				else:
					event_id = -1
			else:
				event_id = self.eit
				if event_id is None:
					event_id = -1

			prep_res = self.record_service.prepare(self.Filename + self.record_service.getFilenameExtension(), self.begin, self.end, event_id, name.replace("\n", ""), description.replace("\n", ""), ' '.join(self.tags), bool(self.descramble), bool(self.record_ecm))
			if prep_res:
				if prep_res == -255:
					self.log(4, "failed to write meta information")
				else:
					self.log(2, "'prepare' failed: error %d" % prep_res)

				# We must calculate start time before stopRecordService call
				# because in Screens/Standby.py TryQuitMainloop tries to get
				# the next start time in evEnd event handler...
				self.do_backoff()
				self.start_prepare = time() + self.backoff

				NavigationInstance.instance.stopRecordService(self.record_service)
				self.record_service = None
				self.setRecordingPreferredTuner(setdefault=True)
				return False
			return True

	def do_backoff(self):
		if self.backoff == 0:
			self.backoff = 5
		else:
			self.backoff *= 2
			if self.backoff > 100:
				self.backoff = 100
		self.log(10, "backoff: retry in %d seconds" % self.backoff)

# Report the tuner that the current recording is using
	def log_tuner(self, level, state):
		feinfo = self.record_service and self.record_service.frontendInfo()
		if feinfo:
			fedata = feinfo.getFrontendData()
			tn = fedata.get("tuner_number") if fedata else -1
			if tn >= 0:
				tuner_info = "Tuner " + chr(ord('A') + tn)
			else:
				tuner_info = SystemInfo["HDMIin"] and "HDMI-IN" or "Unknown source"
		else:
			tuner_info = "Tuner not (yet) allocated"
		self.log(level, "%s recording from: %s" % (state, tuner_info))

	def activate(self):
		next_state = self.state + 1
		self.log(5, "activating state %d" % next_state)

		if next_state == self.StatePrepared:
			if not self.justplay and not self.freespace():
				if self.MountPathErrorNumber < 3 and self.MountPathRetryCounter < 3:
					self.MountPathRetryCounter += 1
					self.start_prepare = time() + 5 # tryPrepare in 5 seconds
					self.log(0, "next try in 5 seconds ...(%d/3)" % self.MountPathRetryCounter)
					return False
				message = _("Error while preparing to record. %s\n%s") % ((_("Disk was not found!"), _("Disk is not writable!"), _("Disk full?"))[self.MountPathErrorNumber-1],self.name)
				Notifications.AddPopup(message, MessageBox.TYPE_ERROR, timeout=20, id="DiskFullMessage")
				self.failed = True
				self.next_activation = time()
				self.lastend = self.end
				self.end = time() + 5
				self.backoff = 0
				return True

			if self.always_zap:
				if Screens.Standby.inStandby:
					self.wasInStandby = True
					eActionMap.getInstance().bindAction('', -maxint - 1, self.keypress)
					# Set service to zap after standby
					Screens.Standby.inStandby.prev_running_service = self.service_ref.ref
					Screens.Standby.inStandby.paused_service = None
					# Wakeup standby
					Screens.Standby.inStandby.Power()
					self.log(5, "wakeup and zap to recording service")
				else:
					cur_zap_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
					if cur_zap_ref and not cur_zap_ref.getPath():  # Do not zap away if it is not a live service
						if self.checkingTimeshiftRunning():
							if self.ts_dialog is None:
								self.openChoiceActionBeforeZap()
						else:
							Notifications.AddNotification(MessageBox, _("In order to record a timer, the TV was switched to the recording service!\n"), type=MessageBox.TYPE_INFO, timeout=20)
							self.setRecordingPreferredTuner()
							self.failureCB(True)
							self.log(5, "zap to recording service")

			if self.tryPrepare():
				self.log(6, "prepare ok, waiting for begin")
				# Create file to "reserve" the filename
				# because another recording at the same time
				# on another service can try to record the same event
				# i.e. cable / sat.. then the second recording needs an own extension...
				# If we create the file
				# here then calculateFilename is kept happy
				if not self.justplay:
					open(self.Filename + self.record_service.getFilenameExtension(), "w").close()
					# Give the Trashcan a chance to clean up
					# Need try/except as Trashcan.instance may not exist
					# for a missed recording started at boot-time.
					try:
						Trashcan.instance.cleanIfIdle()
					except Exception, e:
						print "[RecordTimer] Failed to call Trashcan.instance.cleanIfIdle()"
						print "[RecordTimer] Error:", e
				# Fine. It worked, resources are allocated.
				self.next_activation = self.begin
				self.backoff = 0
				return True
			self.log(7, "prepare failed")
			if eStreamServer.getInstance().getConnectedClients():
				eStreamServer.getInstance().stopStream()
				return False

			if self.first_try_prepare or (self.ts_dialog is not None and not self.checkingTimeshiftRunning()):
				self.first_try_prepare = False
				cur_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
				if cur_ref and not cur_ref.getPath():
					if self.always_zap:
						return False
					if Screens.Standby.inStandby:
						self.setRecordingPreferredTuner()
						self.failureCB(True)
					elif self.checkingTimeshiftRunning():
						if self.ts_dialog is None:
							self.openChoiceActionBeforeZap()
					elif not config.recording.asktozap.value:
						self.log(8, "asking user to zap away")
						Notifications.AddNotificationWithCallback(self.failureCB, MessageBox, _("A timer failed to record!\nDisable TV and try again?\n"), timeout=20)
					else:  # Zap without asking
						self.log(9, "zap without asking")
						Notifications.AddNotification(MessageBox, _("In order to record a timer, the TV was switched to the recording service!\n"), type=MessageBox.TYPE_INFO, timeout=20)
						self.setRecordingPreferredTuner()
						self.failureCB(True)
				elif cur_ref:
					self.log(8, "currently running service is not a live service.. so stop it makes no sense")
				else:
					self.log(8, "currently no service running... so we dont need to stop it")
			return False

		elif next_state == self.StateRunning:
			global wasRecTimerWakeup
			if os.path.exists("/tmp/was_rectimer_wakeup") and not wasRecTimerWakeup:
				wasRecTimerWakeup = int(open("/tmp/was_rectimer_wakeup", "r").read()) and True or False
				os.remove("/tmp/was_rectimer_wakeup")

			# If this timer has been cancelled or has failed,
			# just go to "end" state.
			if self.cancelled:
				return True

			if self.failed:
				return True

			if self.justplay:
				if Screens.Standby.inStandby:
					self.wasInStandby = True
					eActionMap.getInstance().bindAction('', -maxint - 1, self.keypress)
					self.log(11, "wakeup and zap")
					# Set service to zap after standby
					Screens.Standby.inStandby.prev_running_service = self.service_ref.ref
					Screens.Standby.inStandby.paused_service = None
					# Wakeup standby
					Screens.Standby.inStandby.Power()
				else:
					if self.checkingTimeshiftRunning():
						if self.ts_dialog is None:
							self.openChoiceActionBeforeZap()
					else:
						self.log(11, "zapping")

# If there is a MoviePlayer active it will set things back to the
# original channel after it finishes (which will be after we run).
# So for that case, stop the player and defer our zap...which
# lets the player shutdown and do all of its fiddling before we start.
# Repeated every 1s until done.
# IPTV bouquet playing manages on its own - it's just a service.
# Plugins (e.g. Kodi) are another matter...currently ignored.
# Also, could just call failureCB(True) after closing MoviePlayer...
#
						from Screens.InfoBar import MoviePlayer
						if MoviePlayer.instance is not None and MoviePlayer.instance.execing:
							# This is one of the more weirdly named functions, it actually
							# functions as setMoviePlayerInactive
							NavigationInstance.instance.isMovieplayerActive()
# next_state is StateRunning but we can leave self.begin unchanged
							return False

						self._zapToTimerService()
				return True
			else:
				record_res = self.record_service.start()
				self.setRecordingPreferredTuner(setdefault=True)
				if record_res:
					self.log(13, "start recording error: %d" % record_res)
					self.do_backoff()
					# Retry
					self.begin = time() + self.backoff
					return False
				self.log_tuner(11, "start")
				return True

		elif next_state == self.StateEnded or next_state == self.StateFailed:
			old_end = self.end
			self.ts_dialog = None
			if self.setAutoincreaseEnd():
				self.log(12, "autoincrease recording %d minute(s)" % int((self.end - old_end) / 60))
				self.state -= 1
				return True
			self.log_tuner(12, "stop")
			RecordingsState(-1)
			if not self.justplay:
				if self.record_service:
					NavigationInstance.instance.stopRecordService(self.record_service)
					self.record_service = None
			if self.lastend and self.failed:
				self.end = self.lastend

			NavigationInstance.instance.RecordTimer.saveTimer()

# From here on we are checking whether to put the box into Standby or
# Deep Standby.
# Don't even *bother* checking this if a playback is in progress or an
# IPTV channel is active (unless we are in Standby - in which case it
# isn't really in playback or active)
# ....just say the timer has been handled.
# Trying to back off isn't worth it as backing off in Record timers
# currently only refers to *starting* a recording.
#
			from Components.Converter.ClientsStreaming import ClientsStreaming
			if not Screens.Standby.inStandby and NavigationInstance.instance.getCurrentlyPlayingServiceReference() and (
				'0:0:0:0:0:0:0:0:0' in NavigationInstance.instance.getCurrentlyPlayingServiceReference().toString() or
				'4097:' in NavigationInstance.instance.getCurrentlyPlayingServiceReference().toString()
			):
				return True

			if self.afterEvent == AFTEREVENT.STANDBY or (not wasRecTimerWakeup and Screens.Standby.inStandby and self.afterEvent == AFTEREVENT.AUTO) or self.wasInStandby:
				self.keypress()  # This unbinds the keypress detection
				if not Screens.Standby.inStandby:  # Not already in standby
					Notifications.AddNotificationWithCallback(self.sendStandbyNotification, MessageBox, _("A finished record timer wants to set your %s %s to standby mode.\nGo to standby mode now?") % (getMachineBrand(), getMachineName()), timeout=180)
			elif self.afterEvent == AFTEREVENT.DEEPSTANDBY or (wasRecTimerWakeup and self.afterEvent == AFTEREVENT.AUTO and Screens.Standby.inStandby):
				if NavigationInstance.instance.RecordTimer.recordingsActive(900, useStillRecording=True):
					print '[RecordTimer] Recording or Recording due is next 15 mins, not return to deepstandby'
					return True

# Also check for someone streaming remotely - in which case we don't
# want DEEPSTANDBY.
# Might consider going to standby instead, but probably not worth it...
# Also might want to back off - but that is set-up for trying to start
# recordings, so has a low maximum delay.
#
				from Components.Converter.ClientsStreaming import ClientsStreaming
				if int(ClientsStreaming("NUMBER").getText()) > 0:
					if not Screens.Standby.inStandby:  # not already in standby
						Notifications.AddNotificationWithCallback(
							self.sendStandbyNotification, MessageBox,
							_("A finished record timer wants to set your %s %s to standby mode.\nGo to standby mode now?") % (getMachineBrand(), getMachineName())
							+ _("\n(DeepStandby request changed to Standby owing to there being streaming clients.)"), timeout=180)
					return True
#
				if not Screens.Standby.inTryQuitMainloop:  # The shutdown messagebox is not open
					if Screens.Standby.inStandby:  # In standby
						quitMainloop(Screens.Standby.QUIT_SHUTDOWN)
					else:
						Notifications.AddNotificationWithCallback(self.sendTryQuitMainloopNotification, MessageBox, _("A finished record timer wants to shut down your %s %s.\nShut down now?") % (getMachineBrand(), getMachineName()), timeout=180)
			return True

	def _zapToTimerService(self):
		def serviceInBouquet(bouquet, serviceHandler, ref):
			servicelist = serviceHandler.list(bouquet)
			if servicelist is not None:
				serviceIterator = servicelist.getNext()
				while serviceIterator.valid():
					if ref == serviceIterator:
						return True
					serviceIterator = servicelist.getNext()
			return False

		from Screens.ChannelSelection import ChannelSelection
		ChannelSelectionInstance = ChannelSelection.instance
		if ChannelSelectionInstance:
			self.service_types = service_types_tv
			self.service_types_ref = service_types_tv_ref
			foundService = False
			serviceHandler = eServiceCenter.getInstance()
			if config.usage.multibouquet.value:
				bqroot = eServiceReference(self.service_types_ref)
				bqroot.setPath('FROM BOUQUET "bouquets.tv" ORDER BY bouquet')
				rootbouquet = bqroot
				currentBouquet = ChannelSelectionInstance.getRoot()
				for searchCurrent in (True, False):
					bouquet = eServiceReference(bqroot)
					bouquetlist = serviceHandler.list(bouquet)
					if bouquetlist is not None:
						bouquet = bouquetlist.getNext()
						while bouquet.valid():
							if bouquet.flags & eServiceReference.isDirectory and (currentBouquet is None or (currentBouquet == bouquet) == searchCurrent):
								foundService = serviceInBouquet(bouquet, serviceHandler, self.service_ref.ref)
								if foundService:
									break
							bouquet = bouquetlist.getNext()
						if foundService:
							break
			else:
				bqroot = serviceRefAppendPath(self.service_types_ref, ' FROM BOUQUET "userbouquet.favourites.tv" ORDER BY bouquet')
				rootbouquet = bqroot
				bouquet = eServiceReference(bqroot)
				if bouquet.valid() and bouquet.flags & eServiceReference.isDirectory:
					foundService = serviceInBouquet(bouquet, serviceHandler, self.service_ref.ref)

			if foundService:
				ChannelSelectionInstance.setRoot(bouquet)
				ChannelSelectionInstance.clearPath()
				ChannelSelectionInstance.enterPath(rootbouquet)
				if config.usage.multibouquet.value:
					ChannelSelectionInstance.enterPath(bouquet)
				ChannelSelectionInstance.saveRoot()
				ChannelSelectionInstance.saveChannel(self.service_ref.ref)
				ChannelSelectionInstance.addToHistory(self.service_ref.ref)
				NavigationInstance.instance.playService(self.service_ref.ref)
			else:
				self.log(1, "zap failed: bouquet not found for zap service")
		else:
			self.log(1, "zap failed: channel selection service not available")

	def keypress(self, key=None, flag=1):
		if flag and self.wasInStandby:
			self.wasInStandby = False
			eActionMap.getInstance().unbindAction('', self.keypress)

	def setAutoincreaseEnd(self, entry=None):
		if not self.autoincrease:
			return False
		if entry is None:
			new_end = int(time()) + self.autoincreasetime
		else:
			new_end = entry.begin - 30

		dummyentry = RecordTimerEntry(
			self.service_ref, self.begin, new_end, self.name, self.description, self.eit, disabled=True,
			justplay=self.justplay, afterEvent=self.afterEvent, dirname=self.dirname, tags=self.tags)
		dummyentry.disabled = self.disabled
		timersanitycheck = TimerSanityCheck(NavigationInstance.instance.RecordTimer.timer_list, dummyentry)
		if not timersanitycheck.check():
			simulTimerList = timersanitycheck.getSimulTimerList()
			if simulTimerList is not None and len(simulTimerList) > 1:
				new_end = simulTimerList[1].begin
				new_end -= 30  # Allow 30 seconds preparation time
		if new_end <= time():
			return False
		self.end = new_end
		return True

	def setRecordingPreferredTuner(self, setdefault=False):
		if self.needChangePriorityFrontend:
			elem = None
			if not self.change_frontend and not setdefault:
				elem = (self.setAdvancedPriorityFrontend is not None and self.setAdvancedPriorityFrontend) or config.usage.recording_frontend_priority.value
				self.change_frontend = True
			elif self.change_frontend and setdefault:
				elem = config.usage.frontend_priority.value
				self.change_frontend = False
				self.setAdvancedPriorityFrontend = None
			if elem is not None:
				setPreferredTuner(int(elem))

	def checkingTimeshiftRunning(self):
		return config.usage.check_timeshift.value and self.InfoBarInstance and self.InfoBarInstance.timeshiftEnabled() and self.InfoBarInstance.isSeekable()

	def openChoiceActionBeforeZap(self):
		if self.ts_dialog is None:
			type = _("record")
			if self.justplay:
				type = _("zap")
			elif self.always_zap:
				type = _("zap and record")
			message = _("You must switch to the service %s (%s - '%s')!\n") % (type, self.service_ref.getServiceName(), self.name)
			if self.repeated:
				message += _("Attention, this is repeated timer!\n")
			message += _("Timeshift is running. Select an action.\n")
			choice = [(_("Zap"), "zap"), (_("Don't zap and disable timer"), "disable"), (_("Don't zap and remove timer"), "remove")]
			if not self.InfoBarInstance.save_timeshift_file:
				choice.insert(0, (_("Save timeshift and zap"), "save"))
			else:
				message += _("Reminder, you have chosen to save timeshift file.")
			# if self.justplay or self.always_zap:
			# 	choice.insert(2, (_("Don't zap"), "continue"))
			choice.insert(2, (_("Don't zap"), "continue"))

			def zapAction(choice):
				start_zap = True
				if choice:
					if choice in ("zap", "save"):
						self.log(8, "zap to recording service")
						if choice == "save":
							ts = self.InfoBarInstance.getTimeshift()
							if ts and ts.isTimeshiftEnabled():
								del ts
								self.InfoBarInstance.save_timeshift_file = True
								self.InfoBarInstance.SaveTimeshift()
					elif choice == "disable":
						self.disable()
						NavigationInstance.instance.RecordTimer.timeChanged(self)
						start_zap = False
						self.log(8, "zap canceled by the user, timer disabled")
					elif choice == "remove":
						start_zap = False
						self.afterEvent = AFTEREVENT.NONE
						NavigationInstance.instance.RecordTimer.removeEntry(self)
						self.log(8, "zap canceled by the user, timer removed")
					elif choice == "continue":
						if self.justplay:
							self.end = self.begin
						start_zap = False
						self.log(8, "zap canceled by the user")
				if start_zap:
					if not self.justplay:
						self.setRecordingPreferredTuner()
						self.failureCB(True)
					else:
						self.log(8, "zapping")
						NavigationInstance.instance.playService(self.service_ref.ref)
			self.ts_dialog = self.InfoBarInstance.session.openWithCallback(zapAction, MessageBox, message, simple=True, list=choice, timeout=20)

	def sendStandbyNotification(self, answer):
		if answer:
			Notifications.AddNotification(Screens.Standby.Standby)

	def sendTryQuitMainloopNotification(self, answer):
		if answer:
			Notifications.AddNotification(Screens.Standby.TryQuitMainloop, Screens.Standby.QUIT_SHUTDOWN)
		else:
			global wasRecTimerWakeup
			wasRecTimerWakeup = False

	def getNextActivation(self):
		self.isStillRecording = False
		if self.state == self.StateEnded or self.state == self.StateFailed:
			if self.end > time():
				self.isStillRecording = True
			return self.end
		next_state = self.state + 1
		if next_state == self.StateEnded or next_state == self.StateFailed:
			if self.end > time():
				self.isStillRecording = True
		return {
			self.StatePrepared: self.start_prepare,
			self.StateRunning: self.begin,
			self.StateEnded: self.end
		}[next_state]

	def failureCB(self, answer):
		if answer:
			self.log(13, "ok, zapped away")
			# NavigationInstance.instance.stopUserServices()
			self._zapToTimerService()
		else:
			self.log(14, "user didn't want to zap away, record will probably fail")

	def timeChanged(self):
		old_prepare = self.start_prepare
		self.start_prepare = self.begin - self.prepare_time
		self.backoff = 0

		if int(old_prepare) > 60 and int(old_prepare) != int(self.start_prepare):
			self.log(15, "record time changed, start prepare is now: %s" % ctime(self.start_prepare))

	def gotRecordEvent(self, record, event):
		# TODO: this is not working (never true), please fix (comparing two swig wrapped ePtrs).
		if self.__record_service.__deref__() != record.__deref__():
			return
		# self.log(16, "record event %d" % event)
		if event == iRecordableService.evRecordWriteError:
			if self.record_service:
				NavigationInstance.instance.stopRecordService(self.record_service)
				self.record_service = None
			self.failed = True
			self.lastend = self.end
			self.end = time() + 5
			self.backoff = 0
			msg, err = self.freespace(True)
			self.log(16, "WRITE ERROR while recording, %s" % msg)
			print "WRITE ERROR on recording, %s" % msg
			# show notification. the 'id' will make sure that it will be
			# displayed only once, even if more timers are failing at the
			# same time. (which is very likely in case of disk fullness)
			Notifications.AddPopup(text = _("Write error while recording. %s") %(_("An unknown error occurred!"), _("Disk was not found!"), _("Disk is not writable!"), _("Disk full?"))[err], type = MessageBox.TYPE_ERROR, timeout = 0, id = "DiskFullMessage")
			# ok, the recording has been stopped. we need to properly note
			# that in our state, with also keeping the possibility to re-try.
			# TODO: this has to be done.
		elif event == iRecordableService.evStart:
			RecordingsState(1)
			text = _("A recording has been started:\n%s") % self.name
			notify = config.usage.show_message_when_recording_starts.value and not Screens.Standby.inStandby and self.InfoBarInstance and self.InfoBarInstance.execing
			if self.dirnameHadToFallback:
				text = '\n'.join((text, _("Please note that the previously selected media could not be accessed and therefore the default directory is being used instead.")))
				notify = True
			if notify:
				Notifications.AddPopup(text=text, type=MessageBox.TYPE_INFO, timeout=3, id="RecStart" + getattr(self, "Filename", ''))
		elif event == iRecordableService.evRecordAborted:
			NavigationInstance.instance.RecordTimer.removeEntry(self)
		elif event == iRecordableService.evGstRecordEnded:
			if self.repeated:
				self.processRepeated(findRunningEvent=False)
			NavigationInstance.instance.RecordTimer.doActivate(self)

	# We have record_service as property to automatically subscribe to record service events
	def setRecordService(self, service):
		if self.__record_service is not None:
			# print "[RecordTimer][remove callback]"
			NavigationInstance.instance.record_event.remove(self.gotRecordEvent)

		self.__record_service = service

		if self.__record_service is not None:
			# print "[RecordTimer][add callback]"
			NavigationInstance.instance.record_event.append(self.gotRecordEvent)

	record_service = property(lambda self: self.__record_service, setRecordService)

def createTimer(xml):
	begin = int(xml.get("begin"))
	end = int(xml.get("end"))
	serviceref = ServiceReference(xml.get("serviceref").encode("utf-8"))
	description = xml.get("description").encode("utf-8")
	repeated = xml.get("repeated").encode("utf-8")
	rename_repeat = long(xml.get("rename_repeat") or "1")
	disabled = long(xml.get("disabled") or "0")
	justplay = long(xml.get("justplay") or "0")
	always_zap = long(xml.get("always_zap") or "0")
	afterevent = str(xml.get("afterevent") or "nothing")
	afterevent = {
		"nothing": AFTEREVENT.NONE,
		"standby": AFTEREVENT.STANDBY,
		"deepstandby": AFTEREVENT.DEEPSTANDBY,
		"auto": AFTEREVENT.AUTO
	}[afterevent]
	eit = xml.get("eit")
	if eit and eit != "None":
		eit = long(eit)
	else:
		eit = None
	location = xml.get("location")
	if location and location != "None":
		location = location.encode("utf-8")
	else:
		location = None
	tags = xml.get("tags")
	if tags and tags != "None":
		tags = tags.encode("utf-8").split(' ')
	else:
		tags = None
	descramble = int(xml.get("descramble") or "1")
	record_ecm = int(xml.get("record_ecm") or "0")
	isAutoTimer = int(xml.get("isAutoTimer") or "0")
	ice_timer_id = xml.get("ice_timer_id")
	if ice_timer_id:
		ice_timer_id = ice_timer_id.encode("utf-8")
	name = xml.get("name").encode("utf-8")
	# filename = xml.get("filename").encode("utf-8")
	entry = RecordTimerEntry(
		serviceref, begin, end, name, description, eit, disabled, justplay, afterevent,
		dirname=location, tags=tags, descramble=descramble, record_ecm=record_ecm,
		isAutoTimer=isAutoTimer, ice_timer_id=ice_timer_id, always_zap=always_zap,
		rename_repeat=rename_repeat)
	entry.repeated = int(repeated)

	for l in xml.findall("log"):
		time = int(l.get("time"))
		code = int(l.get("code"))
		msg = l.text.strip().encode("utf-8")
		entry.log_entries.append((time, code, msg))

	return entry

class RecordTimer(timer.Timer):
	def __init__(self):
		timer.Timer.__init__(self)

		self.onTimerAdded = []
		self.onTimerRemoved = []
		self.onTimerChanged = []

		self.Filename = Directories.resolveFilename(Directories.SCOPE_CONFIG, "timers.xml")

		try:
			self.loadTimer()
		except IOError:
			print "[RecordTimer] unable to load timers from file!"

	def timeChanged(self, entry):
		timer.Timer.timeChanged(self, entry)
		for f in self.onTimerChanged:
			f(entry)

	def cleanup(self):
		for entry in self.processed_timers[:]:
			if not entry.disabled:
				self.processed_timers.remove(entry)
				for f in self.onTimerRemoved:
					f(entry)
		self.saveTimer()

	def doActivate(self, w):
		# If the timer should be skipped (e.g. disabled or
		# its end time has past), simply abort the timer.
		# Don't run through all the states.
		if w.shouldSkip():
			w.state = RecordTimerEntry.StateEnded
		else:
			# If active returns true, this means "accepted".
			# Otherwise, the current state is kept.
			# The timer entry itself will fix up the delay.
			if w.activate():
				w.state += 1

		try:
			self.timer_list.remove(w)
		except:
			print '[RecordTimer] Remove list failed'

		# Did this timer reach the final state?
		if w.state < RecordTimerEntry.StateEnded:
			# No, sort it into active list
			insort(self.timer_list, w)
		else:
			# Yes. Process repeat if necessary, and re-add.
			if w.repeated:
				w.processRepeated()
				w.state = RecordTimerEntry.StateWaiting
				w.first_try_prepare = True
				self.addTimerEntry(w)
			else:
				# Check for disabled timers whose end time has passed
				self.cleanupDisabled()
				# Remove old timers as set in config
				self.cleanupDaily(config.recording.keep_timers.value)
				insort(self.processed_timers, w)
		self.stateChanged(w)

	def isRecTimerWakeup(self):
		return wasRecTimerWakeup

	def isRecording(self):
		isRunning = False
		for timer in self.timer_list:
			if timer.isRunning() and not timer.justplay:
				isRunning = True
		return isRunning

	def loadTimer(self):
		try:
			f = open(self.Filename, 'r')
			doc = xml.etree.cElementTree.parse(f)
			f.close()
		except SyntaxError:
			from Tools.Notifications import AddPopup
			from Screens.MessageBox import MessageBox

			AddPopup(_("The timer file (timers.xml) is corrupt and could not be loaded."), type=MessageBox.TYPE_ERROR, timeout=0, id="TimerLoadFailed")

			print "[RecordTimer] timers.xml failed to load!"
			try:
				os.rename(self.Filename, self.Filename + "_old")
			except (IOError, OSError):
				print "[RecordTimer] renaming broken timer failed"
			return
		except IOError:
			print "[RecordTimer] timers.xml not found!"
			return

		root = doc.getroot()

		# Post a message if there are timer overlaps in the timer file
		checkit = True
		for timer in root.findall("timer"):
			newTimer = createTimer(timer)
			if (self.record(newTimer, True, dosave=False) is not None) and (checkit is True):
				from Tools.Notifications import AddPopup
				from Screens.MessageBox import MessageBox
				AddPopup(_("Timer overlap in timers.xml detected!\nPlease recheck it!"), type=MessageBox.TYPE_ERROR, timeout=0, id="TimerLoadFailed")
				checkit = False  # The message only needs to be displayed once

	def saveTimer(self):
		list = ['<?xml version="1.0" ?>\n', '<timers>\n']

		for timer in self.timer_list + self.processed_timers:
			if timer.dontSave:
				continue
			list.append('<timer')
			list.append(' begin="' + str(int(timer.begin)) + '"')
			list.append(' end="' + str(int(timer.end)) + '"')
			list.append(' serviceref="' + stringToXML(str(timer.service_ref)) + '"')
			list.append(' repeated="' + str(int(timer.repeated)) + '"')
			list.append(' rename_repeat="' + str(int(timer.rename_repeat)) + '"')
			list.append(' name="' + str(stringToXML(timer.name)) + '"')
			list.append(' description="' + str(stringToXML(timer.description)) + '"')
			list.append(' afterevent="' + str(stringToXML({
				AFTEREVENT.NONE: "nothing",
				AFTEREVENT.STANDBY: "standby",
				AFTEREVENT.DEEPSTANDBY: "deepstandby",
				AFTEREVENT.AUTO: "auto"
			}[timer.afterEvent])) + '"')
			if timer.eit is not None:
				list.append(' eit="' + str(timer.eit) + '"')
			if timer.dirname is not None:
				list.append(' location="' + str(stringToXML(timer.dirname)) + '"')
			if timer.tags is not None:
				list.append(' tags="' + str(stringToXML(' '.join(timer.tags))) + '"')
			list.append(' disabled="' + str(int(timer.disabled)) + '"')
			list.append(' justplay="' + str(int(timer.justplay)) + '"')
			list.append(' always_zap="' + str(int(timer.always_zap)) + '"')
			list.append(' descramble="' + str(int(timer.descramble)) + '"')
			list.append(' record_ecm="' + str(int(timer.record_ecm)) + '"')
			list.append(' isAutoTimer="' + str(int(timer.isAutoTimer)) + '"')
			if timer.ice_timer_id is not None:
				list.append(' ice_timer_id="' + str(timer.ice_timer_id) + '"')
			list.append('>\n')

# 		Handle repeat entries, which never end and so never get pruned by cleanupDaily
#       Repeating timers get, e.g., repeated="127" (dow bitmap)

			ignore_before = 0
			if config.recording.keep_timers.value > 0:
				if int(timer.repeated) > 0:
					ignore_before = time() - config.recording.keep_timers.value * 86400

			for log_time, code, msg in timer.log_entries:
				if log_time < ignore_before:
					continue
				list.append('<log')
				list.append(' code="' + str(code) + '"')
				list.append(' time="' + str(log_time) + '"')
				list.append('>')
				list.append(str(stringToXML(msg)))
				list.append('</log>\n')

			list.append('</timer>\n')

		list.append('</timers>\n')

		try:
			f = open(self.Filename + ".writing", "w")
			for x in list:
				f.write(x)
			f.flush()

			os.fsync(f.fileno())
			f.close()
			os.rename(self.Filename + ".writing", self.Filename)
		except:
			print "There is not /etc/enigma2/timers.xml file !!! Why ?? "

	def getNextZapTime(self, from_time=None):
		now = from_time if from_time is not None else time()
		for timer in self.timer_list:
			if not timer.justplay or timer.begin < now:
				continue
			return timer.begin
		return -1

	def getStillRecording(self):
		isStillRecording = False
		now = time()
		for timer in self.timer_list:
			if timer.isStillRecording:
				isStillRecording = True
				break
			elif abs(timer.begin - now) <= 10:
				isStillRecording = True
				break
		return isStillRecording

	def getNextRecordingTimeOld(self, from_time=None):
		now = from_time if from_time is not None else time()
		for timer in self.timer_list:
			next_act = timer.getNextActivation()
			if timer.justplay or next_act < now:
				continue
			return next_act
		return -1

	def getNextRecordingTime(self, from_time=None):
		nextrectime = self.getNextRecordingTimeOld(from_time=from_time)
		faketime = time() + 300

		if config.timeshift.isRecording.value:
			if 0 < nextrectime < faketime:
				return nextrectime
			else:
				return faketime
		else:
			return nextrectime

	# from_time allows the recordingsActive() test to be done
	# relative to a particular time (normally the activation time
	# when comparing two timers).
	def recordingsActive(self, margin, from_time=None, useStillRecording=False):
		now = time()
		if from_time is None:
			from_time = now
		return (
			(self.getStillRecording() if useStillRecording else self.isRecording()) or
			abs(self.getNextRecordingTime(from_time=from_time) - now) <= margin or
			abs(self.getNextZapTime(from_time=from_time) - now) <= margin
		)

	def isNextRecordAfterEventActionAuto(self):
		for timer in self.timer_list:
			if timer.justplay:
				continue
			if timer.afterEvent == AFTEREVENT.AUTO or timer.afterEvent == AFTEREVENT.DEEPSTANDBY:
				return True
		return False

	def record(self, entry, ignoreTSC=False, dosave=True):  # Called by loadTimer with dosave=False
		timersanitycheck = TimerSanityCheck(self.timer_list, entry)
		if not timersanitycheck.check():
			if not ignoreTSC:
				print "[RecordTimer] timer conflict detected!"
				return timersanitycheck.getSimulTimerList()
			else:
				print "[RecordTimer] ignore timer conflict"
		elif timersanitycheck.doubleCheck():
			print "[RecordTimer] ignore double timer"
			return None
		entry.timeChanged()
		print "[RecordTimer] Record " + str(entry)
		entry.Timer = self
		self.addTimerEntry(entry)

		# Trigger onTimerAdded callbacks
		for f in self.onTimerAdded:
			f(entry)

		if dosave:
			self.saveTimer()

		return None

	def isInTimer(self, eventid, begin, duration, service):
		returnValue = None
		kind = 0
		time_match = 0

		isAutoTimer = 0
		bt = None
		check_offset_time = not config.recording.margin_before.value and not config.recording.margin_after.value
		end = begin + duration
		refstr = ':'.join(service.split(':')[:11])
		for x in self.timer_list:
			isAutoTimer = 0
			if x.isAutoTimer == 1:
				isAutoTimer |= 1
			if x.ice_timer_id is not None:
				isAutoTimer |= 2
			check = ':'.join(x.service_ref.ref.toString().split(':')[:11]) == refstr
			if not check:
				sref = x.service_ref.ref
				parent_sid = sref.getUnsignedData(5)
				parent_tsid = sref.getUnsignedData(6)
				if parent_sid and parent_tsid:
					# Check for subservice
					sid = sref.getUnsignedData(1)
					tsid = sref.getUnsignedData(2)
					sref.setUnsignedData(1, parent_sid)
					sref.setUnsignedData(2, parent_tsid)
					sref.setUnsignedData(5, 0)
					sref.setUnsignedData(6, 0)
					check = sref.toCompareString() == refstr
					num = 0
					if check:
						check = False
						event = eEPGCache.getInstance().lookupEventId(sref, eventid)
						num = event and event.getNumOfLinkageServices() or 0
					sref.setUnsignedData(1, sid)
					sref.setUnsignedData(2, tsid)
					sref.setUnsignedData(5, parent_sid)
					sref.setUnsignedData(6, parent_tsid)
					for cnt in range(num):
						subservice = event.getLinkageService(sref, cnt)
						if sref.toCompareString() == subservice.toCompareString():
							check = True
							break
			if check:
				timer_end = x.end
				timer_begin = x.begin
				kind_offset = 0
				if not x.repeated and check_offset_time:
					if 0 < end - timer_end <= 59:
						timer_end = end
					elif 0 < timer_begin - begin <= 59:
						timer_begin = begin
				if x.justplay:
					kind_offset = 5
					if (timer_end - x.begin) <= 1:
						timer_end += 60
				if x.always_zap:
					kind_offset = 10

				if x.repeated != 0:
					if bt is None:
						bt = localtime(begin)
						bday = bt.tm_wday
						begin2 = 1440 + bt.tm_hour * 60 + bt.tm_min
						end2 = begin2 + duration / 60
					xbt = localtime(x.begin)
					xet = localtime(timer_end)
					offset_day = False
					checking_time = x.begin < begin or begin <= x.begin <= end
					if xbt.tm_yday != xet.tm_yday:
						oday = bday - 1
						if oday == -1:
							oday = 6
						offset_day = x.repeated & (1 << oday)
					xbegin = 1440 + xbt.tm_hour * 60 + xbt.tm_min
					xend = xbegin + ((timer_end - x.begin) / 60)
					if xend < xbegin:
						xend += 1440
					if x.repeated & (1 << bday) and checking_time:
						if begin2 < xbegin <= end2:
							if xend < end2:
								# Recording within event
								time_match = (xend - xbegin) * 60
								kind = kind_offset + 3
							else:
								# Recording last part of event
								time_match = (end2 - xbegin) * 60
								kind = kind_offset + 1
						elif xbegin <= begin2 <= xend:
							if xend < end2:
								# Recording first part of event
								time_match = (xend - begin2) * 60
								kind = kind_offset + 4
							else:
								# Recording whole event
								time_match = (end2 - begin2) * 60
								kind = kind_offset + 2
						elif offset_day:
							xbegin -= 1440
							xend -= 1440
							if begin2 < xbegin <= end2:
								if xend < end2:
									# Recording within event
									time_match = (xend - xbegin) * 60
									kind = kind_offset + 3
								else:
									# Recording last part of event
									time_match = (end2 - xbegin) * 60
									kind = kind_offset + 1
							elif xbegin <= begin2 <= xend:
								if xend < end2:
									# Recording first part of event
									time_match = (xend - begin2) * 60
									kind = kind_offset + 4
								else:
									# Recording whole event
									time_match = (end2 - begin2) * 60
									kind = kind_offset + 2
					elif offset_day and checking_time:
						xbegin -= 1440
						xend -= 1440
						if begin2 < xbegin <= end2:
							if xend < end2:
								# Recording within event
								time_match = (xend - xbegin) * 60
								kind = kind_offset + 3
							else:
								# Recording last part of event
								time_match = (end2 - xbegin) * 60
								kind = kind_offset + 1
						elif xbegin <= begin2 <= xend:
							if xend < end2:
								# Recording first part of event
								time_match = (xend - begin2) * 60
								kind = kind_offset + 4
							else:
								# Recording whole event
								time_match = (end2 - begin2) * 60
								kind = kind_offset + 2
				else:
					if begin < timer_begin <= end:
						if timer_end < end:
							# Recording within event
							time_match = timer_end - timer_begin
							kind = kind_offset + 3
						else:
							# Recording last part of event
							time_match = end - timer_begin
							kind = kind_offset + 1
					elif timer_begin <= begin <= timer_end:
						if timer_end < end:
							# Recording first part of event
							time_match = timer_end - begin
							kind = kind_offset + 4
						else:  # Recording whole event
							time_match = end - begin
							kind = kind_offset + 2

				if time_match:
					returnValue = (time_match, kind, isAutoTimer)
					if kind in (2, 7, 12):  # When full recording do not look further
						break
		return returnValue

	def removeEntry(self, entry):
		# print "[RecordTimer] Remove " + str(entry)

		# Avoid re-enqueuing
		entry.repeated = False

		# Abort timer.
		# This sets the end time to current time, so timer will be stopped.
		entry.autoincrease = False
		entry.abort()

		if entry.state != entry.StateEnded:
			self.timeChanged(entry)

# 		print "[RecordTimer]state: ", entry.state
# 		print "[RecordTimer]in processed: ", entry in self.processed_timers
# 		print "[RecordTimer]in running: ", entry in self.timer_list

		# Autoincrease instant timer if possible
		if not entry.dontSave:
			for x in self.timer_list:
				if x.setAutoincreaseEnd():
					self.timeChanged(x)
		# Now the timer should be in the processed_timers list.
		# Remove it from there.
		if entry in self.processed_timers:
			self.processed_timers.remove(entry)

		# Trigger onTimerRemoved callbacks
		for f in self.onTimerRemoved:
			f(entry)

		self.saveTimer()

	def shutdown(self):
		self.saveTimer()
