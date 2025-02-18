import locale
import os
import skin
from time import time
from boxbranding import getBrandOEM, getBoxType

from enigma import eDVBDB, eEPGCache, setTunerTypePriorityOrder, setPreferredTuner, setSpinnerOnOff, setEnableTtCachingOnOff, eEnv, Misc_Options, eBackgroundFileEraser, eServiceEvent, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_TOP, RT_WRAP

from Components.About import about
from Components.Harddisk import harddiskmanager
from config import ConfigSubsection, ConfigYesNo, config, ConfigSelection, ConfigText, ConfigNumber, ConfigSet, ConfigLocations, NoSave, ConfigClock, ConfigInteger, ConfigBoolean, ConfigPassword, ConfigIP, ConfigSlider, ConfigSelectionNumber
from Tools.Directories import resolveFilename, SCOPE_HDD, SCOPE_TIMESHIFT, defaultRecordingLocation
from Components.NimManager import nimmanager
from Components.ServiceList import refreshServiceList
from SystemInfo import SystemInfo

def InitUsageConfig():
	config.misc.useNTPminutes = ConfigSelection(default="30", choices=[
		("30", "30 " + _("minutes")),
		("60", "1 " + _("hour")),
		("120", "2 " + _("hours")),
		("240", "4 " + _("hours")),
		("360", "6 " + _("hours")),
		("480", "8 " + _("hours")),
		("720", "12 " + _("hours")),
		("1440", "24 " + _("hours")),
		])

	if getBrandOEM() in ('vuplus', ):
		config.misc.remotecontrol_text_support = ConfigYesNo(default=True)
	else:
		config.misc.remotecontrol_text_support = ConfigYesNo(default=False)

	config.usage = ConfigSubsection()
	config.usage.showdish = ConfigSelection(default="flashing", choices=[("flashing", _("Flashing")), ("normal", _("Not Flashing")), ("off", _("Off"))])
	config.misc.showrotorposition = ConfigSelection(default = "no", choices = [("no", _("no")), ("yes", _("yes")), ("withtext", _("with text")), ("tunername", _("with tuner name"))])
	config.usage.multibouquet = ConfigYesNo(default=True)

	config.usage.alternative_number_mode = ConfigYesNo(default=True)

	def alternativeNumberModeChange(configElement):
		eDVBDB.getInstance().setNumberingMode(configElement.value)
		refreshServiceList()

	config.usage.alternative_number_mode.addNotifier(alternativeNumberModeChange)

	config.usage.servicetype_icon_mode = ConfigSelection(default="0", choices=[("0", _("None")), ("1", _("Left from servicename")), ("2", _("Right from servicename"))])
	config.usage.servicetype_icon_mode.addNotifier(refreshServiceList)
	config.usage.crypto_icon_mode = ConfigSelection(default="0", choices=[("0", _("None")), ("1", _("Left from servicename")), ("2", _("Right from servicename"))])
	config.usage.crypto_icon_mode.addNotifier(refreshServiceList)
	config.usage.record_indicator_mode = ConfigSelection(default="3", choices=[("0", _("None")), ("1", _("Left from servicename")), ("2", _("Right from servicename")), ("3", _("Red colored"))])
	config.usage.record_indicator_mode.addNotifier(refreshServiceList)

	choicelist = [("-1", _("Disable"))]
	for i in range(0, 1300, 25):
		choicelist.append((str(i), ngettext("%d pixel wide", "%d pixels wide", i) % i))
	config.usage.servicelist_column = ConfigSelection(default="-1", choices=choicelist)
	config.usage.servicelist_column.addNotifier(refreshServiceList)

	config.usage.service_icon_enable = ConfigYesNo(default=True)
	config.usage.service_icon_enable.addNotifier(refreshServiceList)
	config.usage.servicelist_cursor_behavior = ConfigSelection(default="keep", choices=[
		("standard", _("Standard")),
		("keep", _("Keep service")),
		("reverseB", _("Reverse bouquet buttons")),
		("keep reverseB", _("Keep service") + " + " + _("Reverse bouquet buttons"))])

	config.usage.multiepg_ask_bouquet = ConfigYesNo(default=False)

	# config.usage.defaultEPGType sets the guide type for
	# the INFO button

	config.usage.defaultEPGType = ConfigSelection(default="None", choices=[])
	if config.usage.defaultEPGType.saved_value is not None:
		config.usage.defaultEPGType.setChoices([config.usage.defaultEPGType.saved_value])
		config.usage.defaultEPGType.load()

	# config.usage.defaultGuideType sets the guide type for
	# the EPG button

	config.usage.defaultGuideType = ConfigSelection(default="None", choices=[])
	if config.usage.defaultGuideType.saved_value is not None:
		config.usage.defaultGuideType.setChoices([config.usage.defaultGuideType.saved_value])
		config.usage.defaultGuideType.load()

	config.usage.panicbutton = ConfigYesNo(default=False)
	config.usage.quickzap_bouquet_change = ConfigYesNo(default=False)
	config.usage.e1like_radio_mode = ConfigYesNo(default=True)

	choicelist = [("0", _("No timeout"))]
	for i in range(1, 10) + range(10, 91, 10):
		choicelist.append((str(i), ngettext("%d second", "%d seconds", i) % i))
	config.usage.infobar_timeout = ConfigSelection(default = "5", choices = choicelist)
	config.usage.show_infobar_do_dimming = ConfigYesNo(default=True)
	config.usage.show_infobar_dimming_speed = ConfigSelectionNumber(min=1, max=40, stepwidth=1, default=40, wraparound=True)
	config.usage.show_infobar_on_zap = ConfigYesNo(default=True)
	config.usage.show_infobar_on_skip = ConfigYesNo(default=True)
	config.usage.show_infobar_on_event_change = ConfigYesNo(default=False)

	config.usage.show_infobar_channel_number = ConfigYesNo(default=False)
	config.usage.show_second_infobar = ConfigYesNo(default=True)
	config.usage.second_infobar_timeout = ConfigSelection(default="0", choices=[("0", _("no timeout"))] + choicelist)
	config.usage.infobar_frontend_source = ConfigSelection(default="tuner", choices=[("settings", _("Settings")), ("tuner", _("Tuner"))])

	config.usage.show_picon_bkgrn = ConfigSelection(default="transparent", choices=[("none", _("Disabled")), ("transparent", _("Transparent")), ("blue", _("Blue")), ("red", _("Red")), ("black", _("Black")), ("white", _("White")), ("lightgrey", _("Light Grey")), ("grey", _("Grey"))])
	config.usage.show_genre_info = ConfigYesNo(default=True)
	config.usage.menu_show_numbers = ConfigYesNo(default = False)
	config.usage.show_menupath = ConfigSelection(default = "small", choices = [("off", _("None")), ("small", _("Small")), ("large", _("Large"))])
	config.usage.show_spinner = ConfigYesNo(default=True)
	config.usage.enable_tt_caching = ConfigYesNo(default=True)
	config.usage.sort_settings = ConfigYesNo(default=False)
	config.usage.sort_menus = ConfigYesNo(default=False)
	config.usage.sort_pluginlist = ConfigYesNo(default=True)
	config.usage.movieplayer_pvrstate = ConfigYesNo(default=True)

	choicelist = []
	for i in (10, 30):
		choicelist.append((str(i), ngettext("%d second", "%d seconds", i) % i))
	for i in (60, 120, 300, 600, 1200, 1800):
		m = i / 60
		choicelist.append((str(i), ngettext("%d minute", "%d minutes", m) % m))
	for i in (3600, 7200, 14400):
		h = i / 3600
		choicelist.append((str(i), ngettext("%d hour", "%d hours", h) % h))
	config.usage.hdd_standby = ConfigSelection(default="300", choices=[("0", _("No standby"))] + choicelist)
	config.usage.output_12V = ConfigSelection(default="do not change", choices=[
		("do not change", _("Do not change")), ("off", _("Off")), ("on", _("On"))])

	config.usage.pip_zero_button = ConfigSelection(default="standard", choices=[
		("standard", _("Standard")), ("swap", _("Swap PiP and main picture")),
		("swapstop", _("Move PiP to main picture")), ("stop", _("Stop PiP"))])
	config.usage.pip_hideOnExit = ConfigSelection(default="no", choices=[
		("no", _("No")), ("popup", _("With popup")), ("without popup", _("Without popup"))])
	choicelist = [("-1", _("Disabled")), ("0", _("No timeout"))]
	for i in [60, 300, 600, 900, 1800, 2700, 3600]:
		m = i / 60
		choicelist.append((str(i), ngettext("%d minute", "%d minutes", m) % m))
	config.usage.pip_last_service_timeout = ConfigSelection(default="0", choices=choicelist)

	if not os.path.exists(resolveFilename(SCOPE_HDD)):
		try:
			os.mkdir(resolveFilename(SCOPE_HDD), 0755)
		except:
			pass
	config.usage.default_path = ConfigText(default=resolveFilename(SCOPE_HDD))
	if not config.usage.default_path.value.endswith('/'):
		tmpvalue = config.usage.default_path.value
		config.usage.default_path.setValue(tmpvalue + '/')
		config.usage.default_path.save()

	def defaultpathChanged(configElement):
		if not config.usage.default_path.value.endswith('/'):
			tmpvalue = config.usage.default_path.value
			config.usage.default_path.setValue(tmpvalue + '/')
			config.usage.default_path.save()

	config.usage.default_path.addNotifier(defaultpathChanged, immediate_feedback=False)

	config.usage.timer_path = ConfigText(default="<default>")
	config.usage.instantrec_path = ConfigText(default="<default>")

	if not os.path.exists(resolveFilename(SCOPE_TIMESHIFT)):
		try:
			os.mkdir(resolveFilename(SCOPE_TIMESHIFT), 0755)
		except:
			pass
	config.usage.timeshift_path = ConfigText(default=resolveFilename(SCOPE_TIMESHIFT))
	if not config.usage.default_path.value.endswith('/'):
		tmpvalue = config.usage.timeshift_path.value
		config.usage.timeshift_path.setValue(tmpvalue + '/')
		config.usage.timeshift_path.save()

	def timeshiftpathChanged(configElement):
		if not config.usage.timeshift_path.value.endswith('/'):
			tmpvalue = config.usage.timeshift_path.value
			config.usage.timeshift_path.setValue(tmpvalue + '/')
			config.usage.timeshift_path.save()

	config.usage.timeshift_path.addNotifier(timeshiftpathChanged, immediate_feedback=False)
	config.usage.allowed_timeshift_paths = ConfigLocations(default=[resolveFilename(SCOPE_TIMESHIFT)])

#GML:1
	config.usage.trashsort_deltime = ConfigSelection(default = "no", choices = [
		("no", _("no")),
		("show record time", _("Yes, show record time")),
		("show delete time", _("Yes, show delete time"))])
	config.usage.movielist_trashcan = ConfigYesNo(default=True)
	config.usage.movielist_asktrash = ConfigYesNo(default=False)
	config.usage.movielist_trashcan_network_clean = ConfigYesNo(default=False)

#GML:2
	config.usage.movielist_trashcan_days = ConfigSelectionNumber(default=8, min=0, max=31, stepwidth=1, wraparound=True)
	config.usage.movielist_trashcan_reserve = ConfigNumber(default=40)
	config.usage.movielist_resume_cache_max = ConfigSelection(default="1000", choices=[("0", _("Disabled")), ("100", "100"), ("200", "200"), ("500", "500"), ("1000", "1000"), ("2000", "2000"), ("5000", "5000")])
	config.usage.on_movie_start = ConfigSelection(default="ask yes", choices=[
		("ask yes", _("Ask user (with default as 'yes')")),
		("ask no", _("Ask user (with default as 'no')")),
		("resume", _("Resume from last position")),
		("beginning", _("Start from the beginning"))])
	config.usage.on_movie_stop = ConfigSelection(default="movielist", choices=[
		("ask", _("Ask user")),
		("movielist", _("Return to movie list")),
		("quit", _("Return to previous service"))])
	config.usage.on_movie_eof = ConfigSelection(default="movielist", choices=[
		("ask", _("Ask user")),
		("movielist", _("Return to movie list")),
		("quit", _("Return to previous service")),
		("pause", _("Pause movie at end")),
		("playlist", _("Play next (return to movie list)")),
		("playlistquit", _("Play next (return to previous service)")),
		("loop", _("Continues play (loop)")),
		("repeatcurrent", _("Repeat"))])
	config.usage.leave_movieplayer_onExit = ConfigSelection(default="no", choices=[
		("no", _("No")),
		("popup", _("With popup")),
		("without popup", _("Without popup"))])
	config.usage.next_movie_msg = ConfigYesNo(default=True)
	config.usage.last_movie_played = ConfigText()

	config.usage.setup_level = ConfigSelection(default="expert", choices=[
		("simple", _("Simple")),
		("intermediate", _("Intermediate")),
		("expert", _("Expert"))])

	config.usage.help_sortorder = ConfigSelection(default="headings+alphabetic", choices=[
		("headings+alphabetic", _("Alphabetical under headings")),
		("flat+alphabetic", _("Flat alphabetical")),
		("flat+remotepos", _("Flat by position on remote")),
		("flat+remotegroups", _("Flat by key group on remote"))])

	config.usage.short_power_enable = ConfigYesNo(default=True)

	# Only intended for use in "requires" attributes in setup.xml
	config.usage.short_power_disable = NoSave(ConfigBoolean(default=not config.usage.short_power_enable.value))

	def doDisableShortPower(configElement):
		config.usage.short_power_disable.value = not configElement.value

	config.usage.short_power_enable.addNotifier(doDisableShortPower)

	config.usage.on_long_powerpress = ConfigSelection(default="show_menu", choices=[
		("show_menu", _("Show shutdown menu")),
		("shutdown", _("Immediate shutdown")),
		("standby", _("Standby"))])

	config.usage.on_short_powerpress = ConfigSelection(default="standby", choices=[
		("show_menu", _("Show shutdown menu")),
		("shutdown", _("Immediate shutdown")),
		("standby", _("Standby"))])

	choicelist = [("0", "Disabled")]
	for i in (5, 30, 60, 300, 600, 900, 1200, 1800, 2700, 3600):
		if i < 60:
			m = ngettext("%d second", "%d seconds", i) % i
		else:
			m = abs(i / 60)
			m = ngettext("%d minute", "%d minutes", m) % m
		choicelist.append(("%d" % i, m))
	config.usage.screen_saver = ConfigSelection(default="0", choices=choicelist)

	config.usage.check_timeshift = ConfigYesNo(default=True)

	config.usage.alternatives_priority = ConfigSelection(default="5", choices=[
		("0", "DVB-S/-C/-T"),
		("1", "DVB-S/-T/-C"),
		("2", "DVB-C/-S/-T"),
		("3", "DVB-C/-T/-S"),
		("4", "DVB-T/-C/-S"),
		("5", "DVB-T/-S/-C"),
		("127", "No priority")])

	def remote_fallback_changed(configElement):
		if configElement.value:
			configElement.value = "%s%s" % (not configElement.value.startswith("http://") and "http://" or "", configElement.value)
			configElement.value = "%s%s" % (configElement.value, configElement.value.count(":") == 1 and ":8001" or "")
	config.usage.remote_fallback_enabled = ConfigYesNo(default=False)
	config.usage.remote_fallback = ConfigText(default="", fixed_size=False)
	config.usage.remote_fallback.addNotifier(remote_fallback_changed, immediate_feedback=False);

	config.usage.timer_sanity_check_enabled = ConfigYesNo(default = True);

	dvbs_nims = [("-2", _("Disabled"))]
	dvbt_nims = [("-2", _("Disabled"))]
	dvbc_nims = [("-2", _("Disabled"))]
	atsc_nims = [("-2", _("Disabled"))]

	nims = [("-1", _("auto"))]
	rec_nims = [("-2", _("Disabled")), ("-1", _("auto"))]
	for x in nimmanager.nim_slots:
		if x.isCompatible("DVB-S"):
			dvbs_nims.append((str(x.slot), x.getSlotName()))
		elif x.isCompatible("DVB-T"):
			dvbt_nims.append((str(x.slot), x.getSlotName()))
		elif x.isCompatible("DVB-C"):
			dvbc_nims.append((str(x.slot), x.getSlotName()))
		elif x.isCompatible("ATSC"):
			atsc_nims.append((str(x.slot), x.getSlotName()))
		nims.append((str(x.slot), x.getSlotName()))
		rec_nims.append((str(x.slot), x.getSlotName()))
	try:
		config.usage.frontend_priority = ConfigSelection(default="0", choices=nims)
	except:
		config.usage.frontend_priority = ConfigSelection(default="-1", choices=nims)
	config.usage.recording_frontend_priority = ConfigSelection(default="-2", choices=rec_nims)
	config.misc.disable_background_scan = ConfigYesNo(default=False)
	config.usage.frontend_priority_dvbs = ConfigSelection(default = "-2", choices = list(dvbs_nims))
	dvbs_nims.insert(1,("-1", _("auto")))
	config.usage.jobtaskextensions = ConfigYesNo(default = True)
	config.usage.recording_frontend_priority_dvbs = ConfigSelection(default = "-2", choices = dvbs_nims)
	config.usage.frontend_priority_dvbt = ConfigSelection(default = "-2", choices = list(dvbt_nims))
	dvbt_nims.insert(1,("-1", _("auto")))
	config.usage.recording_frontend_priority_dvbt = ConfigSelection(default = "-2", choices = dvbt_nims)
	config.usage.frontend_priority_dvbc = ConfigSelection(default = "-2", choices = list(dvbc_nims))
	dvbc_nims.insert(1,("-1", _("auto")))
	config.usage.recording_frontend_priority_dvbc = ConfigSelection(default = "-2", choices = dvbc_nims)
	config.usage.frontend_priority_atsc = ConfigSelection(default = "-2", choices = list(atsc_nims))
	atsc_nims.insert(1,("-1", _("auto")))
	config.usage.recording_frontend_priority_atsc = ConfigSelection(default = "-2", choices = atsc_nims)

	SystemInfo["DVB-S_priority_tuner_available"] = len(dvbs_nims) > 3 and any(len(i) > 2 for i in (dvbt_nims, dvbc_nims, atsc_nims))
	SystemInfo["DVB-T_priority_tuner_available"] = len(dvbt_nims) > 3 and any(len(i) > 2 for i in (dvbs_nims, dvbc_nims, atsc_nims))
	SystemInfo["DVB-C_priority_tuner_available"] = len(dvbc_nims) > 3 and any(len(i) > 2 for i in (dvbs_nims, dvbt_nims, atsc_nims))
	SystemInfo["ATSC_priority_tuner_available"] = len(atsc_nims) > 3 and any(len(i) > 2 for i in (dvbs_nims, dvbc_nims, dvbt_nims))

	config.usage.servicenum_fontsize = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.usage.servicename_fontsize = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.usage.serviceinfo_fontsize = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.usage.serviceitems_per_page = ConfigSelectionNumber(default=10, stepwidth=1, min=1, max=40, wraparound=True)
	config.usage.show_servicelist = ConfigYesNo(default=True)
	config.usage.servicelist_mode = ConfigSelection(default="standard", choices=[
		("standard", _("Standard")),
		("simple", _("Slim"))])
	config.usage.servicelistpreview_mode = ConfigYesNo(default=False)
	config.usage.tvradiobutton_mode = ConfigSelection(default="BouquetList", choices=[
		("ChannelList", _("Channel List")),
		("BouquetList", _("Bouquet List")),
		("MovieList", _("Movie List"))])
	config.usage.channelbutton_mode = ConfigSelection(default="0", choices=[
		("0", _("Just change channels")),
		("1", _("Channel List")),
		("2", _("Bouquet List"))])
	config.usage.show_bouquetalways = ConfigYesNo(default=False)
	config.usage.show_event_progress_in_servicelist = ConfigSelection(default='barright', choices=[
		('barleft', _("Progress bar left")),
		('barright', _("Progress bar right")),
		('percleft', _("Percentage left")),
		('percright', _("Percentage right")),
		('no', _("No"))])
	config.usage.show_channel_numbers_in_servicelist = ConfigYesNo(default=True)
	config.usage.show_channel_jump_in_servicelist = ConfigSelection(default="alpha", choices=[
		("quick", _("Quick actions")),
		("alpha", _("Alpha search")),
		("number", _("Number search"))])

	config.usage.show_event_progress_in_servicelist.addNotifier(refreshServiceList)
	config.usage.show_channel_numbers_in_servicelist.addNotifier(refreshServiceList)

	if SystemInfo["7segment"]:
		# standby
		config.usage.blinking_display_clock_during_recording = ConfigSelection(default="Rec", choices=[
			("Rec", _("REC")),
			("RecBlink", _("Blinking REC")),
			("Time", _("Time")),
			("Nothing", _("Nothing"))])
		config.usage.show_in_standby = ConfigSelection(default="time", choices=[
			("time", _("Time")),
			("nothing", _("Nothing"))])
		# in use
		config.usage.blinking_rec_symbol_during_recording = ConfigSelection(default="Rec", choices=[
			("Rec", _("REC")),
			("RecBlink", _("Blinking REC")),
			("Time", _("Time"))])
	else:
		config.usage.blinking_display_clock_during_recording = ConfigYesNo(default=False)

	config.usage.show_message_when_recording_starts = ConfigYesNo(default=False)
	config.usage.on_short_recpress = ConfigSelection(default="menu", choices=[])
	config.usage.on_long_recpress = ConfigSelection(default="menu", choices=[])

	config.usage.load_length_of_movies_in_moviellist = ConfigYesNo(default=True)
	config.usage.show_icons_in_movielist = ConfigSelection(default='i', choices=[
		('o', _("Off")),
		('p', _("Progress")),
		('s', _("Small progress")),
		('i', _("Icons")),
	])
	config.usage.movielist_unseen = ConfigYesNo(default=True)

	config.usage.swap_snr_on_osd = ConfigYesNo(default=False)
	config.usage.swap_time_display_on_osd = ConfigSelection(default="0", choices=[("0", _("Skin Setting")), ("1", _("Mins")), ("2", _("Mins Secs")), ("3", _("Hours Mins")), ("4", _("Hours Mins Secs")), ("5", _("Percentage"))])
	config.usage.swap_media_time_display_on_osd = ConfigSelection(default="0", choices=[("0", _("Skin Setting")), ("1", _("Mins")), ("2", _("Mins Secs")), ("3", _("Hours Mins")), ("4", _("Hours Mins Secs")), ("5", _("Percentage"))])
	config.usage.swap_time_remaining_on_osd = ConfigSelection(default="0", choices=[("0", _("Remaining")), ("1", _("Elapsed")), ("2", _("Elapsed & Remaining")), ("3", _("Remaining & Elapsed"))])
	config.usage.elapsed_time_positive_osd = ConfigYesNo(default=False)
	config.usage.swap_time_display_on_vfd = ConfigSelection(default="0", choices=[("0", _("Skin Setting")), ("1", _("Mins")), ("2", _("Mins Secs")), ("3", _("Hours Mins")), ("4", _("Hours Mins Secs")), ("5", _("Percentage"))])
	config.usage.swap_media_time_display_on_vfd = ConfigSelection(default="0", choices=[("0", _("Skin Setting")), ("1", _("Mins")), ("2", _("Mins Secs")), ("3", _("Hours Mins")), ("4", _("Hours Mins Secs")), ("5", _("Percentage"))])
	config.usage.swap_time_remaining_on_vfd = ConfigSelection(default="0", choices=[("0", _("Remaining")), ("1", _("Elapsed")), ("2", _("Elapsed & Remaining")), ("3", _("Remaining & Elapsed"))])
	config.usage.elapsed_time_positive_vfd = ConfigYesNo(default=False)

	config.usage.lcd_scroll_delay = ConfigSelection(default="10000", choices=[
		("10000", "10 " + _("seconds")),
		("20000", "20 " + _("seconds")),
		("30000", "30 " + _("seconds")),
		("60000", "1 " + _("minute")),
		("300000", "5 " + _("minutes")),
		("noscrolling", _("off"))])
	config.usage.lcd_scroll_speed = ConfigSelection(default="300", choices=[
		("500", _("slow")),
		("300", _("normal")),
		("100", _("fast"))])

	def SpinnerOnOffChanged(configElement):
		setSpinnerOnOff(int(configElement.value))

	config.usage.show_spinner.addNotifier(SpinnerOnOffChanged)

	def EnableTtCachingChanged(configElement):
		setEnableTtCachingOnOff(int(configElement.value))

	config.usage.enable_tt_caching.addNotifier(EnableTtCachingChanged)

	def TunerTypePriorityOrderChanged(configElement):
		setTunerTypePriorityOrder(int(configElement.value))

	config.usage.alternatives_priority.addNotifier(TunerTypePriorityOrderChanged, immediate_feedback=False)

	def PreferredTunerChanged(configElement):
		setPreferredTuner(int(configElement.value))

	config.usage.frontend_priority.addNotifier(PreferredTunerChanged)

	config.usage.hide_zap_errors = ConfigYesNo(default=True)
	config.usage.hide_ci_messages = ConfigYesNo(default=True)
	config.usage.show_cryptoinfo = ConfigSelection(default="0", choices=[("0", _("Off")), ("1", _("One line")), ("2", _("Two lines"))])
	config.usage.show_eit_nownext = ConfigYesNo(default=True)
	config.usage.show_vcr_scart = ConfigYesNo(default=False)
	config.usage.pic_resolution = ConfigSelection(default=None, choices=[(None, _("Same resolution as skin")), ("(720, 576)", "720x576"), ("(1280, 720)", "1280x720"), ("(1920, 1080)", "1920x1080")])

	config.usage.date = ConfigSubsection()
	config.usage.date.enabled = NoSave(ConfigBoolean(default=False))
	config.usage.date.enabled_display = NoSave(ConfigBoolean(default=False))
	config.usage.time = ConfigSubsection()
	config.usage.time.enabled = NoSave(ConfigBoolean(default=False))
	config.usage.time.disabled = NoSave(ConfigBoolean(default=True))
	config.usage.time.enabled_display = NoSave(ConfigBoolean(default=False))
	config.usage.time.wide = NoSave(ConfigBoolean(default=False))
	config.usage.time.wide_display = NoSave(ConfigBoolean(default=False))

	# TRANSLATORS: full date representation dayname daynum monthname year in strftime() format! See 'man strftime'
	config.usage.date.dayfull = ConfigSelection(default=_("%A %-d %B %Y"), choices=[
		(_("%A %d %B %Y"), _("Dayname DD Month Year")),
		(_("%A %-d %B %Y"), _("Dayname D Month Year")),
		(_("%A %d-%B-%Y"), _("Dayname DD-Month-Year")),
		(_("%A %-d-%B-%Y"), _("Dayname D-Month-Year")),
		(_("%A %d/%m/%Y"), _("Dayname DD/MM/Year")),
		(_("%A %-d/%m/%Y"), _("Dayname D/MM/Year")),
		(_("%A %d/%-m/%Y"), _("Dayname DD/M/Year")),
		(_("%A %-d/%-m/%Y"), _("Dayname D/M/Year")),
		(_("%A %B %d %Y"), _("Dayname Month DD Year")),
		(_("%A %B %-d %Y"), _("Dayname Month D Year")),
		(_("%A %B-%d-%Y"), _("Dayname Month-DD-Year")),
		(_("%A %B-%-d-%Y"), _("Dayname Month-D-Year")),
		(_("%A %m/%d/%Y"), _("Dayname MM/DD/Year")),
		(_("%A %-m/%d/%Y"), _("Dayname M/DD/Year")),
		(_("%A %m/%-d/%Y"), _("Dayname MM/D/Year")),
		(_("%A %-m/%-d/%Y"), _("Dayname M/D/Year")),
		(_("%A %Y %B %d"), _("Dayname Year Month DD")),
		(_("%A %Y %B %-d"), _("Dayname Year Month D")),
		(_("%A %Y-%B-%d"), _("Dayname Year-Month-DD")),
		(_("%A %Y-%B-%-d"), _("Dayname Year-Month-D")),
		(_("%A %Y/%m/%d"), _("Dayname Year/MM/DD")),
		(_("%A %Y/%m/%-d"), _("Dayname Year/MM/D")),
		(_("%A %Y/%-m/%d"), _("Dayname Year/M/DD")),
		(_("%A %Y/%-m/%-d"), _("Dayname Year/M/D"))
	])

	# TRANSLATORS: long date representation short dayname daynum monthname year in strftime() format! See 'man strftime'
	config.usage.date.shortdayfull = ConfigText(default=_("%a %-d %B %Y"))

	# TRANSLATORS: long date representation short dayname daynum short monthname year in strftime() format! See 'man strftime'
	config.usage.date.daylong = ConfigText(default=_("%a %-d %b %Y"))

	# TRANSLATORS: short date representation dayname daynum short monthname in strftime() format! See 'man strftime'
	config.usage.date.dayshortfull = ConfigText(default=_("%A %-d %B"))

	# TRANSLATORS: short date representation short dayname daynum short monthname in strftime() format! See 'man strftime'
	config.usage.date.dayshort = ConfigText(default=_("%a %-d %b"))

	# TRANSLATORS: small date representation short dayname daynum in strftime() format! See 'man strftime'
	config.usage.date.daysmall = ConfigText(default=_("%a %-d"))

	# TRANSLATORS: full date representation daynum monthname year in strftime() format! See 'man strftime'
	config.usage.date.full = ConfigText(default=_("%-d %B %Y"))

	# TRANSLATORS: long date representation daynum short monthname year in strftime() format! See 'man strftime'
	config.usage.date.long = ConfigText(default=_("%-d %b %Y"))

	# TRANSLATORS: small date representation daynum short monthname in strftime() format! See 'man strftime'
	config.usage.date.short = ConfigText(default=_("%-d %b"))

	def setDateStyles(configElement):
		dateStyles = {
			# dayfull            shortdayfull      daylong           dayshortfull   dayshort       daysmall    full           long           short
			_("%A %d %B %Y"): (_("%a %d %B %Y"), _("%a %d %b %Y"), _("%A %d %B"), _("%a %d %b"), _("%a %d"), _("%d %B %Y"), _("%d %b %Y"), _("%d %b")),
			_("%A %-d %B %Y"): (_("%a %-d %B %Y"), _("%a %-d %b %Y"), _("%A %-d %B"), _("%a %-d %b"), _("%a %-d"), _("%-d %B %Y"), _("%-d %b %Y"), _("%-d %b")),
			_("%A %d-%B-%Y"): (_("%a %d-%B-%Y"), _("%a %d-%b-%Y"), _("%A %d-%B"), _("%a %d-%b"), _("%a %d"), _("%d-%B-%Y"), _("%d-%b-%Y"), _("%d-%b")),
			_("%A %-d-%B-%Y"): (_("%a %-d-%B-%Y"), _("%a %-d-%b-%Y"), _("%A %-d-%B"), _("%a %-d-%b"), _("%a %-d"), _("%-d-%B-%Y"), _("%-d-%b-%Y"), _("%-d-%b")),
			_("%A %d/%m/%Y"): (_("%a %d/%m/%Y"), _("%a %d/%m/%Y"), _("%A %d/%m"), _("%a %d/%m"), _("%a %d"), _("%d/%m/%Y"), _("%d/%m/%Y"), _("%d/%m")),
			_("%A %-d/%m/%Y"): (_("%a %-d/%m/%Y"), _("%a %-d/%m/%Y"), _("%A %-d/%m"), _("%a %-d/%m"), _("%a %-d"), _("%-d/%m/%Y"), _("%-d/%m/%Y"), _("%-d/%m")),
			_("%A %d/%-m/%Y"): (_("%a %d/%-m/%Y"), _("%a %d/%-m/%Y"), _("%A %d/%-m"), _("%a %d/%-m"), _("%a %d"), _("%d/%-m/%Y"), _("%d/%-m/%Y"), _("%d/%-m")),
			_("%A %-d/%-m/%Y"): (_("%a %-d/%-m/%Y"), _("%a %-d/%-m/%Y"), _("%A %-d/%-m"), _("%a %-d/%-m"), _("%a %-d"), _("%-d/%-m/%Y"), _("%-d/%-m/%Y"), _("%-d/%-m")),
			_("%A %B %d %Y"): (_("%a %B %d %Y"), _("%a %b %d %Y"), _("%A %B %d"), _("%a %b %d"), _("%a %d"), _("%B %d %Y"), _("%b %d %Y"), _("%b %d")),
			_("%A %B %-d %Y"): (_("%a %B %-d %Y"), _("%a %b %-d %Y"), _("%A %B %-d"), _("%a %b %-d"), _("%a %-d"), _("%B %-d %Y"), _("%b %-d %Y"), _("%b %-d")),
			_("%A %B-%d-%Y"): (_("%a %B-%d-%Y"), _("%a %b-%d-%Y"), _("%A %B-%d"), _("%a %b-%d"), _("%a %d"), _("%B-%d-%Y"), _("%b-%d-%Y"), _("%b-%d")),
			_("%A %B-%-d-%Y"): (_("%a %B-%-d-%Y"), _("%a %b-%-d-%Y"), _("%A %B-%-d"), _("%a %b-%-d"), _("%a %-d"), _("%B-%-d-%Y"), _("%b-%-d-%Y"), _("%b-%-d")),
			_("%A %m/%d/%Y"): (_("%a %m/%d/%Y"), _("%a %m/%d/%Y"), _("%A %m/%d"), _("%a %m/%d"), _("%a %d"), _("%m/%d/%Y"), _("%m/%d/%Y"), _("%m/%d")),
			_("%A %-m/%d/%Y"): (_("%a %-m/%d/%Y"), _("%a %-m/%d/%Y"), _("%A %-m/%d"), _("%a %-m/%d"), _("%a %d"), _("%-m/%d/%Y"), _("%-m/%d/%Y"), _("%-m/%d")),
			_("%A %m/%-d/%Y"): (_("%a %m/%-d/%Y"), _("%a %m/%-d/%Y"), _("%A %m/%-d"), _("%a %m/%-d"), _("%a %-d"), _("%m/%-d/%Y"), _("%m/%-d/%Y"), _("%m/%-d")),
			_("%A %-m/%-d/%Y"): (_("%a %-m/%-d/%Y"), _("%a %-m/%-d/%Y"), _("%A %-m/%-d"), _("%a %-m/%-d"), _("%a %-d"), _("%-m/%-d/%Y"), _("%-m/%-d/%Y"), _("%-m/%-d")),
			_("%A %Y %B %d"): (_("%a %Y %B %d"), _("%a %Y %b %d"), _("%A %B %d"), _("%a %b %d"), _("%a %d"), _("%Y %B %d"), _("%Y %b %d"), _("%b %d")),
			_("%A %Y %B %-d"): (_("%a %Y %B %-d"), _("%a %Y %b %-d"), _("%A %B %-d"), _("%a %b %-d"), _("%a %-d"), _("%Y %B %-d"), _("%Y %b %-d"), _("%b %-d")),
			_("%A %Y-%B-%d"): (_("%a %Y-%B-%d"), _("%a %Y-%b-%d"), _("%A %B-%d"), _("%a %b-%d"), _("%a %d"), _("%Y-%B-%d"), _("%Y-%b-%d"), _("%b-%d")),
			_("%A %Y-%B-%-d"): (_("%a %Y-%B-%-d"), _("%a %Y-%b-%-d"), _("%A %B-%-d"), _("%a %b-%-d"), _("%a %-d"), _("%Y-%B-%-d"), _("%Y-%b-%-d"), _("%b-%-d")),
			_("%A %Y/%m/%d"): (_("%a %Y/%m/%d"), _("%a %Y/%m/%d"), _("%A %m/%d"), _("%a %m/%d"), _("%a %d"), _("%Y/%m/%d"), _("%Y/%m/%d"), _("%m/%d")),
			_("%A %Y/%m/%-d"): (_("%a %Y/%m/%-d"), _("%a %Y/%m/%-d"), _("%A %m/%-d"), _("%a %m/%-d"), _("%a %-d"), _("%Y/%m/%-d"), _("%Y/%m/%-d"), _("%m/%-d")),
			_("%A %Y/%-m/%d"): (_("%a %Y/%-m/%d"), _("%a %Y/%-m/%d"), _("%A %-m/%d"), _("%a %-m/%d"), _("%a %d"), _("%Y/%-m/%d"), _("%Y/%-m/%d"), _("%-m/%d")),
			_("%A %Y/%-m/%-d"): (_("%a %Y/%-m/%-d"), _("%a %Y/%-m/%-d"), _("%A %-m/%-d"), _("%a %-m/%-d"), _("%a %-d"), _("%Y/%-m/%-d"), _("%Y/%-m/%-d"), _("%-m/%-d"))
		}
		style = dateStyles.get(configElement.value, ((_("Invalid")) * 8))
		config.usage.date.shortdayfull.value = style[0]
		config.usage.date.shortdayfull.save()
		config.usage.date.daylong.value = style[1]
		config.usage.date.daylong.save()
		config.usage.date.dayshortfull.value = style[2]
		config.usage.date.dayshortfull.save()
		config.usage.date.dayshort.value = style[3]
		config.usage.date.dayshort.save()
		config.usage.date.daysmall.value = style[4]
		config.usage.date.daysmall.save()
		config.usage.date.full.value = style[5]
		config.usage.date.full.save()
		config.usage.date.long.value = style[6]
		config.usage.date.long.save()
		config.usage.date.short.value = style[7]
		config.usage.date.short.save()

	config.usage.date.dayfull.addNotifier(setDateStyles)

	# TRANSLATORS: full time representation hour:minute:seconds
	if locale.nl_langinfo(locale.AM_STR) and locale.nl_langinfo(locale.PM_STR):
		config.usage.time.long = ConfigSelection(default=_("%T"), choices=[
			(_("%T"), _("HH:mm:ss")),
			(_("%-H:%M:%S"), _("H:mm:ss")),
			(_("%I:%M:%S%^p"), _("hh:mm:ssAM/PM")),
			(_("%-I:%M:%S%^p"), _("h:mm:ssAM/PM")),
			(_("%I:%M:%S%P"), _("hh:mm:ssam/pm")),
			(_("%-I:%M:%S%P"), _("h:mm:ssam/pm")),
			(_("%I:%M:%S"), _("hh:mm:ss")),
			(_("%-I:%M:%S"), _("h:mm:ss"))
		])
	else:
		config.usage.time.long = ConfigSelection(default=_("%T"), choices=[
			(_("%T"), _("HH:mm:ss")),
			(_("%-H:%M:%S"), _("H:mm:ss")),
			(_("%I:%M:%S"), _("hh:mm:ss")),
			(_("%-I:%M:%S"), _("h:mm:ss"))
		])

	# TRANSLATORS: time representation hour:minute:seconds for 24 hour clock or 12 hour clock without AM/PM and hour:minute for 12 hour clocks with AM/PM
	config.usage.time.mixed = ConfigText(default=_("%T"))

	# TRANSLATORS: short time representation hour:minute (Same as "Default")
	config.usage.time.short = ConfigText(default=_("%R"))

	def setTimeStyles(configElement):
		timeStyles = {
			# long      mixed    short
			_("%T"): (_("%T"), _("%R")),
			_("%-H:%M:%S"): (_("%-H:%M:%S"), _("%-H:%M")),
			_("%I:%M:%S%^p"): (_("%I:%M%^p"), _("%I:%M%^p")),
			_("%-I:%M:%S%^p"): (_("%-I:%M%^p"), _("%-I:%M%^p")),
			_("%I:%M:%S%P"): (_("%I:%M%P"), _("%I:%M%P")),
			_("%-I:%M:%S%P"): (_("%-I:%M%P"), _("%-I:%M%P")),
			_("%I:%M:%S"): (_("%I:%M:%S"), _("%I:%M")),
			_("%-I:%M:%S"): (_("%-I:%M:%S"), _("%-I:%M"))
		}
		style = timeStyles.get(configElement.value, ((_("Invalid")) * 2))
		config.usage.time.mixed.value = style[0]
		config.usage.time.mixed.save()
		config.usage.time.short.value = style[1]
		config.usage.time.short.save()
		config.usage.time.wide.value = style[1].endswith(("P", "p"))

	config.usage.time.long.addNotifier(setTimeStyles)

	try:
		dateEnabled, timeEnabled = skin.parameters.get("AllowUserDatesAndTimes", (0, 0))
	except Exception as error:
		print "[UsageConfig] Error loading 'AllowUserDatesAndTimes' skin parameter! (%s)" % error
		dateEnabled, timeEnabled = (0, 0)
	if dateEnabled:
		config.usage.date.enabled.value = True
	else:
		config.usage.date.enabled.value = False
		config.usage.date.dayfull.value = config.usage.date.dayfull.default
	if timeEnabled:
		config.usage.time.enabled.value = True
		config.usage.time.disabled.value = not config.usage.time.enabled.value
	else:
		config.usage.time.enabled.value = False
		config.usage.time.disabled.value = not config.usage.time.enabled.value
		config.usage.time.long.value = config.usage.time.long.default

	# TRANSLATORS: compact date representation (for VFD) daynum short monthname in strftime() format! See 'man strftime'
	config.usage.date.display = ConfigSelection(default=_("%-d %b"), choices=[
		("", _("Hidden / Blank")),
		(_("%d %b"), _("Day DD Mon")),
		(_("%-d %b"), _("Day D Mon")),
		(_("%d-%b"), _("Day DD-Mon")),
		(_("%-d-%b"), _("Day D-Mon")),
		(_("%d/%m"), _("Day DD/MM")),
		(_("%-d/%m"), _("Day D/MM")),
		(_("%d/%-m"), _("Day DD/M")),
		(_("%-d/%-m"), _("Day D/M")),
		(_("%b %d"), _("Day Mon DD")),
		(_("%b %-d"), _("Day Mon D")),
		(_("%b-%d"), _("Day Mon-DD")),
		(_("%b-%-d"), _("Day Mon-D")),
		(_("%m/%d"), _("Day MM/DD")),
		(_("%m/%-d"), _("Day MM/D")),
		(_("%-m/%d"), _("Day M/DD")),
		(_("%-m/%-d"), _("Day M/D"))
	])

	config.usage.date.displayday = ConfigText(default=_("%a %-d+%b_"))
	config.usage.date.display_template = ConfigText(default=_("%-d+%b_"))
	config.usage.date.compact = ConfigText(default=_("%-d+%b_"))
	config.usage.date.compressed = ConfigText(default=_("%-d+%b_"))

	timeDisplayValue = [_("%R")]

	def adjustDisplayDates():
		if timeDisplayValue[0] == "":
			if config.usage.date.display.value == "":  # If the date and time are both hidden output a space to blank the VFD display.
				config.usage.date.compact.value = " "
				config.usage.date.compressed.value = " "
			else:
				config.usage.date.compact.value = config.usage.date.displayday.value
				config.usage.date.compressed.value = config.usage.date.displayday.value
		else:
			if config.usage.time.wide_display.value:
				config.usage.date.compact.value = config.usage.date.display_template.value.replace("_", "").replace("=", "").replace("+", "")
				config.usage.date.compressed.value = config.usage.date.display_template.value.replace("_", "").replace("=", "").replace("+", "")
			else:
				config.usage.date.compact.value = config.usage.date.display_template.value.replace("_", " ").replace("=", "-").replace("+", " ")
				config.usage.date.compressed.value = config.usage.date.display_template.value.replace("_", " ").replace("=", "").replace("+", "")
		config.usage.date.compact.save()
		config.usage.date.compressed.save()

	def setDateDisplayStyles(configElement):
		dateDisplayStyles = {
			# display      displayday     template
			"": ("", ""),
			_("%d %b"): (_("%a %d %b"), _("%d+%b_")),
			_("%-d %b"): (_("%a %-d %b"), _("%-d+%b_")),
			_("%d-%b"): (_("%a %d-%b"), _("%d=%b_")),
			_("%-d-%b"): (_("%a %-d-%b"), _("%-d=%b_")),
			_("%d/%m"): (_("%a %d/%m"), _("%d/%m ")),
			_("%-d/%m"): (_("%a %-d/%m"), _("%-d/%m ")),
			_("%d/%-m"): (_("%a %d/%-m"), _("%d/%-m ")),
			_("%-d/%-m"): (_("%a %-d/%-m"), _("%-d/%-m ")),
			_("%b %d"): (_("%a %b %d"), _("%b+%d ")),
			_("%b %-d"): (_("%a %b %-d"), _("%b+%-d ")),
			_("%b-%d"): (_("%a %b-%d"), _("%b=%d ")),
			_("%b-%-d"): (_("%a %b-%-d"), _("%b=%-d ")),
			_("%m/%d"): (_("%a %m/%d"), _("%m/%d ")),
			_("%m/%-d"): (_("%a %m/%-d"), _("%m/%-d ")),
			_("%-m/%d"): (_("%a %-m/%d"), _("%-m/%d ")),
			_("%-m/%-d"): (_("%a %-m/%-d"), _("%-m/%-d "))
		}
		style = dateDisplayStyles.get(configElement.value, ((_("Invalid")) * 2))
		config.usage.date.displayday.value = style[0]
		config.usage.date.displayday.save()
		config.usage.date.display_template.value = style[1]
		config.usage.date.display_template.save()
		adjustDisplayDates()

	config.usage.date.display.addNotifier(setDateDisplayStyles)

	# TRANSLATORS: short time representation hour:minute (Same as "Default")
	if locale.nl_langinfo(locale.AM_STR) and locale.nl_langinfo(locale.PM_STR):
		config.usage.time.display = ConfigSelection(default=_("%R"), choices=[
			("", _("Hidden / Blank")),
			(_("%R"), _("HH:mm")),
			(_("%-H:%M"), _("H:mm")),
			(_("%I:%M%^p"), _("hh:mmAM/PM")),
			(_("%-I:%M%^p"), _("h:mmAM/PM")),
			(_("%I:%M%P"), _("hh:mmam/pm")),
			(_("%-I:%M%P"), _("h:mmam/pm")),
			(_("%I:%M"), _("hh:mm")),
			(_("%-I:%M"), _("h:mm"))
		])
	else:
		config.usage.time.display = ConfigSelection(default=_("%R"), choices=[
			("", _("Hidden / Blank")),
			(_("%R"), _("HH:mm")),
			(_("%-H:%M"), _("H:mm")),
			(_("%I:%M"), _("hh:mm")),
			(_("%-I:%M"), _("h:mm"))
		])

	def setTimeDisplayStyles(configElement):
		timeDisplayValue[0] = config.usage.time.display.value
		config.usage.time.wide_display.value = configElement.value.endswith(("P", "p"))
		adjustDisplayDates()

	config.usage.time.display.addNotifier(setTimeDisplayStyles)

	try:
		dateDisplayEnabled, timeDisplayEnabled = skin.parameters.get("AllowUserDatesAndTimesDisplay", (0, 0))
	except Exception as error:
		print "[UsageConfig] Error loading 'AllowUserDatesAndTimesDisplay' display skin parameter! (%s)" % error
		dateDisplayEnabled, timeDisplayEnabled = (0, 0)
	if dateDisplayEnabled:
		config.usage.date.enabled_display.value = True
	else:
		config.usage.date.enabled_display.value = False
		config.usage.date.display.value = config.usage.date.display.default
	if timeDisplayEnabled:
		config.usage.time.enabled_display.value = True
	else:
		config.usage.time.enabled_display.value = False
		config.usage.time.display.value = config.usage.time.display.default

	config.usage.boolean_graphic = ConfigYesNo(default=True)

	config.usage.cursorscroll = ConfigSelectionNumber(min=0, max=50, stepwidth=5, default=0, wraparound=True)

	if SystemInfo["hasXcoreVFD"]:
		def set12to8characterVFD(configElement):
			open(SystemInfo["hasXcoreVFD"], "w").write(not configElement.value and "1" or "0")
		config.usage.toggle12to8characterVFD = ConfigYesNo(default = True)
		config.usage.toggle12to8characterVFD.addNotifier(set12to8characterVFD)

	config.epg = ConfigSubsection()
	config.epg.eit = ConfigYesNo(default=True)
	config.epg.mhw = ConfigYesNo(default=False)
	config.epg.freesat = ConfigYesNo(default=False)
	config.epg.viasat = ConfigYesNo(default=False)
	config.epg.netmed = ConfigYesNo(default=False)
	config.epg.virgin = ConfigYesNo(default=False)

	def EpgSettingsChanged(configElement):
		mask = 0xffffffff
		if not config.epg.eit.value:
			mask &= ~(eEPGCache.NOWNEXT | eEPGCache.SCHEDULE | eEPGCache.SCHEDULE_OTHER)
		if not config.epg.mhw.value:
			mask &= ~eEPGCache.MHW
		if not config.epg.freesat.value:
			mask &= ~(eEPGCache.FREESAT_NOWNEXT | eEPGCache.FREESAT_SCHEDULE | eEPGCache.FREESAT_SCHEDULE_OTHER)
		if not config.epg.viasat.value:
			mask &= ~eEPGCache.VIASAT
		if not config.epg.netmed.value:
			mask &= ~(eEPGCache.NETMED_SCHEDULE | eEPGCache.NETMED_SCHEDULE_OTHER)
		if not config.epg.virgin.value:
			mask &= ~(eEPGCache.VIRGIN_NOWNEXT | eEPGCache.VIRGIN_SCHEDULE)
		eEPGCache.getInstance().setEpgSources(mask)

	config.epg.eit.addNotifier(EpgSettingsChanged)
	config.epg.mhw.addNotifier(EpgSettingsChanged)
	config.epg.freesat.addNotifier(EpgSettingsChanged)
	config.epg.viasat.addNotifier(EpgSettingsChanged)
	config.epg.netmed.addNotifier(EpgSettingsChanged)
	config.epg.virgin.addNotifier(EpgSettingsChanged)

	config.epg.histminutes = ConfigSelectionNumber(default=0, min=0, max=120, stepwidth=15, wraparound=True)

	def EpgHistorySecondsChanged(configElement):
		eEPGCache.getInstance().setEpgHistorySeconds(config.epg.histminutes.value * 60)

	config.epg.histminutes.addNotifier(EpgHistorySecondsChanged)

	config.epg.cacheloadsched = ConfigYesNo(default=False)
	config.epg.cachesavesched = ConfigYesNo(default=False)

	def EpgCacheLoadSchedChanged(configElement):
		import EpgLoadSave
		EpgLoadSave.EpgCacheLoadCheck()

	def EpgCacheSaveSchedChanged(configElement):
		import EpgLoadSave
		EpgLoadSave.EpgCacheSaveCheck()

	config.epg.cacheloadsched.addNotifier(EpgCacheLoadSchedChanged, immediate_feedback=False)
	config.epg.cachesavesched.addNotifier(EpgCacheSaveSchedChanged, immediate_feedback=False)
	config.epg.cacheloadtimer = ConfigSelectionNumber(default=24, stepwidth=1, min=1, max=24, wraparound=True)
	config.epg.cachesavetimer = ConfigSelectionNumber(default=24, stepwidth=1, min=1, max=24, wraparound=True)

	hddchoises = [('/etc/enigma2/', 'Internal Flash')]
	for p in harddiskmanager.getMountedPartitions():
		if os.path.exists(p.mountpoint):
			d = os.path.normpath(p.mountpoint)
			if p.mountpoint != '/':
				hddchoises.append((p.mountpoint, d))
	config.misc.epgcachepath = ConfigSelection(default='/etc/enigma2/', choices=hddchoises)
	config.misc.epgcachefilename = ConfigText(default='epg', fixed_size=False)
	config.misc.epgcache_filename = ConfigText(default=(config.misc.epgcachepath.value + config.misc.epgcachefilename.value.replace('.dat', '') + '.dat'))

	def EpgCacheChanged(configElement):
		config.misc.epgcache_filename.setValue(os.path.join(config.misc.epgcachepath.value, config.misc.epgcachefilename.value.replace('.dat', '') + '.dat'))
		config.misc.epgcache_filename.save()
		eEPGCache.getInstance().setCacheFile(config.misc.epgcache_filename.value)
		epgcache = eEPGCache.getInstance()
		epgcache.save()
		if not config.misc.epgcache_filename.value.startswith("/etc/enigma2/"):
			if os.path.exists('/etc/enigma2/' + config.misc.epgcachefilename.value.replace('.dat', '') + '.dat'):
				os.remove('/etc/enigma2/' + config.misc.epgcachefilename.value.replace('.dat', '') + '.dat')

	config.misc.epgcachepath.addNotifier(EpgCacheChanged, immediate_feedback=False)
	config.misc.epgcachefilename.addNotifier(EpgCacheChanged, immediate_feedback=False)

	config.misc.epgratingcountry = ConfigSelection(default="", choices=[("", _("Auto Detect")), ("ETSI", _("Generic")), ("AUS", _("Australia"))])
	config.misc.epggenrecountry = ConfigSelection(default="", choices=[("", _("Auto Detect")), ("ETSI", _("Generic")), ("AUS", _("Australia"))])

	config.misc.showradiopic = ConfigYesNo(default=True)

	def setHDDStandby(configElement):
		for hdd in harddiskmanager.HDDList():
			hdd[1].setIdleTime(int(configElement.value))

	config.usage.hdd_standby.addNotifier(setHDDStandby, immediate_feedback=False)

	if SystemInfo["12V_Output"]:
		def set12VOutput(configElement):
			Misc_Options.getInstance().set_12V_output(configElement.value == "on" and 1 or 0)
		config.usage.output_12V.addNotifier(set12VOutput, immediate_feedback=False)

	config.usage.keymap = ConfigText(default=eEnv.resolve("${datadir}/enigma2/keymap.xml"))

	config.network = ConfigSubsection()
	if SystemInfo["WakeOnLAN"]:
		def wakeOnLANChanged(configElement):
			if getBoxType() in ('et10000', 'gbquadplus', 'gbquad', 'gb800ueplus', 'gb800seplus', 'gbipbox'):
				open(SystemInfo["WakeOnLAN"], "w").write(configElement.value and "on" or "off")
			else:
				open(SystemInfo["WakeOnLAN"], "w").write(configElement.value and "enable" or "disable")
		config.network.wol = ConfigYesNo(default=False)
		config.network.wol.addNotifier(wakeOnLANChanged)
	config.network.AFP_autostart = ConfigYesNo(default=True)
	config.network.NFS_autostart = ConfigYesNo(default=True)
	config.network.OpenVPN_autostart = ConfigYesNo(default=True)
	config.network.Samba_autostart = ConfigYesNo(default=True)
	config.network.Inadyn_autostart = ConfigYesNo(default=True)
	config.network.uShare_autostart = ConfigYesNo(default=True)

	config.softwareupdate = ConfigSubsection()
	config.softwareupdate.check = ConfigYesNo(default=True)
	config.softwareupdate.checktimer = ConfigSelection(choices=[
		("1", "hour"),
		("2", "2 hours"),
		("3", "3 hours"),
		("4", "4 hours"),
		("6", "6 hours"),
		("8", "8 hours"),
		("12", "12 hours"),
		("24", "24 hours"),
		("48", "2 days"),
	], default="1")
	config.softwareupdate.updatefound = NoSave(ConfigBoolean(default=False))
	config.softwareupdate.updatebeta = ConfigYesNo(default=True)
	config.softwareupdate.updateisunstable = ConfigInteger(default=0)
	config.softwareupdate.overwriteConfigFiles = ConfigYesNo(default=False)

	config.timeshift = ConfigSubsection()
	choicelist = [("0", "Disabled")]
	for i in (2, 3, 4, 5, 10, 20, 30):
		choicelist.append(("%d" % i, ngettext("%d second", "%d seconds", i) % i))
	for i in (60, 120, 300):
		m = i / 60
		choicelist.append(("%d" % i, ngettext("%d minute", "%d minutes", m) % m))
	config.timeshift.startdelay = ConfigSelection(default="10", choices=choicelist)
	config.timeshift.showinfobar = ConfigYesNo(default=True)
	config.timeshift.stopwhilerecording = ConfigYesNo(default=False)
	config.timeshift.favoriteSaveAction = ConfigSelection(default="askuser", choices=[("askuser", _("Ask user")), ("savetimeshift", _("Save and stop")), ("savetimeshiftandrecord", _("Save and record")), ("noSave", _("Don't save"))])
	config.timeshift.permanentrecording = ConfigYesNo(default=False)
	config.timeshift.isRecording = NoSave(ConfigYesNo(default=False))
	config.timeshift.stream_warning = ConfigYesNo(default = True)

	config.seek = ConfigSubsection()
	config.seek.autoskip = ConfigYesNo(default=True)
	config.seek.baractivation = ConfigSelection(default="leftright", choices=[("leftright", _("Long Left/Right")), ("ffrw", _("Long << / >>"))])
	config.seek.sensibility = ConfigSelection(default="10", choices=[
		("1", _("0.1%")), ("2", _("0.2%")), ("5", _("0.5%")),
		("10", _("1%")), ("20", _("2%")), ("50", _("5%")),
		("100", _("10%"))])
	config.seek.updown_skips = ConfigYesNo(default=True)
	config.seek.selfdefined_up = ConfigSelectionNumber(default=180, min=1, max=300, stepwidth=1, wraparound=True)
	config.seek.selfdefined_down = ConfigSelectionNumber(default=60, min=1, max=300, stepwidth=1, wraparound=True)
	config.seek.selfdefined_left = ConfigSelectionNumber(default=10, min=1, max=300, stepwidth=1, wraparound=True)
	config.seek.selfdefined_right = ConfigSelectionNumber(default=10, min=1, max=300, stepwidth=1, wraparound=True)
	config.seek.number_skips = ConfigSelection(default="False", choices=[("False", _("No")), ("media", _("Media (zap in timeshift)")), ("True", _("Yes")), ("always", _("Always (enter timeshift if possible)"))])
	config.seek.number_method = ConfigSelection(default="relsec", choices=[("relsec", _("Relative seconds")), ("abspc", _("Absolute percentage"))])
	config.seek.selfdefined_13 = ConfigSelectionNumber(default=30, min=1, max=300, stepwidth=1, wraparound=True)
	config.seek.selfdefined_46 = ConfigSelectionNumber(default=180, min=5, max=1800, stepwidth=5, wraparound=True)
	config.seek.selfdefined_79 = ConfigSelectionNumber(default=300, min=10, max=3600, stepwidth=10, wraparound=True)

	# Only intended for use in "requires" attributes in setup.xml
	config.seek.number_skip_rel = NoSave(ConfigBoolean(default=config.seek.number_skips.value != "False" and config.seek.number_method.value == "relsec"))

	def doEnableNumberSkips(configElement):
		config.seek.number_skip_rel.value = config.seek.number_skips.value != "False" and config.seek.number_method.value == "relsec"

	config.seek.number_skips.addNotifier(doEnableNumberSkips)
	config.seek.number_method.addNotifier(doEnableNumberSkips)

	config.seek.speeds_forward = ConfigSet(default=[2, 4, 8, 16, 32, 64, 128], choices=[2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128])
	config.seek.speeds_backward = ConfigSet(default=[2, 4, 8, 16, 32, 64, 128], choices=[1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128])
	config.seek.speeds_slowmotion = ConfigSet(default=[2, 4, 8], choices=[2, 4, 6, 8, 12, 16, 25])

	config.seek.enter_forward = ConfigSelection(default="2", choices=["2", "4", "6", "8", "12", "16", "24", "32", "48", "64", "96", "128"])
	config.seek.enter_backward = ConfigSelection(default="1", choices=["1", "2", "4", "6", "8", "12", "16", "24", "32", "48", "64", "96", "128"])

	def updateEnterForward(configElement):
		if not configElement.value:
			configElement.value = [2]
		updateChoices(config.seek.enter_forward, configElement.value)

	config.seek.speeds_forward.addNotifier(updateEnterForward, immediate_feedback=False)

	def updateEnterBackward(configElement):
		if not configElement.value:
			configElement.value = [2]
		updateChoices(config.seek.enter_backward, configElement.value)

	config.seek.speeds_backward.addNotifier(updateEnterBackward, immediate_feedback=False)

	config.seek.on_pause = ConfigSelection(default="play", choices=[
		("play", _("Play")),
		("step", _("Single step (GOP)")),
		("last", _("Last speed"))])

	config.crash = ConfigSubsection()
	config.crash.details = ConfigYesNo(default=True)
	config.crash.enabledebug = ConfigYesNo(default=False)
	config.crash.debugloglimit = ConfigSelectionNumber(default=4, min=1, max=10, stepwidth=1, wraparound=True)
	config.crash.daysloglimit = ConfigSelectionNumber(default=8, min=1, max=30, stepwidth=1, wraparound=True)
	config.crash.sizeloglimit = ConfigSelectionNumber(default=10, min=0, max=100, stepwidth=5, wraparound=True)

	debugpath = [('/home/root/logs/', '/home/root/')]
	for p in harddiskmanager.getMountedPartitions():
		if os.path.exists(p.mountpoint):
			d = os.path.normpath(p.mountpoint)
			if p.mountpoint != '/':
				debugpath.append((p.mountpoint + 'logs/', d))
	config.crash.debug_path = ConfigSelection(default="/home/root/logs/", choices=debugpath)

	def updatedebug_path(configElement):
		if not os.path.exists(config.crash.debug_path.value):
			os.mkdir(config.crash.debug_path.value, 0755)

	config.crash.debug_path.addNotifier(updatedebug_path, immediate_feedback=False)
	config.crash.debug_path.callNotifiersOnSaveAndCancel = True

	config.usage.timerlist_finished_timer_position = ConfigSelection(default="end", choices=[("beginning", _("at beginning")), ("end", _("at end"))])

	def updateEraseSpeed(el):
		eBackgroundFileEraser.getInstance().setEraseSpeed(int(el.value))

	def updateEraseFlags(el):
		eBackgroundFileEraser.getInstance().setEraseFlags(int(el.value))

	config.misc.erase_speed = ConfigSelection(default="100", choices=[
		("10", "10 MB/s"),
		("20", "20 MB/s"),
		("50", "50 MB/s"),
		("100", "100 MB/s")])
	config.misc.erase_speed.addNotifier(updateEraseSpeed, immediate_feedback=False)
	config.misc.erase_flags = ConfigSelection(default="0", choices=[
		("0", _("Disable")),
		("1", _("Internal hdd only")),
		("3", _("Everywhere"))])
	config.misc.erase_flags.addNotifier(updateEraseFlags, immediate_feedback=False)

	if SystemInfo["ZapMode"]:
		def setZapmode(el):
			file = open(SystemInfo["ZapMode"], "w")
			file.write(el.value)
			file.close()
		config.misc.zapmode = ConfigSelection(default="mute", choices=[
			("mute", _("Black screen")), ("hold", _("Hold screen")), ("mutetilllock", _("Black screen till locked")), ("holdtilllock", _("Hold till locked"))])
		config.misc.zapmode.addNotifier(setZapmode, immediate_feedback=False)
	config.usage.historymode = ConfigSelection(default="1", choices=[("0", _("Just zap")), ("1", _("Show menu"))])

	if SystemInfo["HasForceLNBOn"]:
		def forceLNBPowerChanged(configElement):
			open(SystemInfo["HasForceLNBOn"], "w").write(configElement.value)
		config.misc.forceLnbPower = ConfigSelection(default = "off", choices = [ ("on", _("Yes")), ("off", _("No"))] )
		config.misc.forceLnbPower.addNotifier(forceLNBPowerChanged)

	if SystemInfo["HasForceToneburst"]:
		def forceToneBurstChanged(configElement):
			open(SystemInfo["HasForceToneburst"], "w").write(configElement.value)
		config.misc.forceToneBurst = ConfigSelection(default = "disable", choices = [ ("enable", _("Yes")), ("disable", _("No"))] )
		config.misc.forceToneBurst.addNotifier(forceToneBurstChanged)

	config.subtitles = ConfigSubsection()
	config.subtitles.ttx_subtitle_colors = ConfigSelection(default="0", choices=[
		("0", _("original")),
		("1", _("white")),
		("2", _("yellow"))])
	config.subtitles.ttx_subtitle_original_position = ConfigYesNo(default=True)
	config.subtitles.ttx_subtitle_position = ConfigSelection(default="50", choices=["0", "10", "20", "30", "40", "50", "60", "70", "80", "90", "100", "150", "200", "250", "300", "350", "400", "450"])
	config.subtitles.subtitle_alignment = ConfigSelection(default="center", choices=[("left", _("left")), ("center", _("center")), ("right", _("right"))])
	config.subtitles.subtitle_rewrap = ConfigYesNo(default=False)
	config.subtitles.colourise_dialogs = ConfigYesNo(default = False)
	config.subtitles.subtitle_borderwidth = ConfigSelection(default="3", choices=["1", "2", "3", "4", "5"])
	# Teletext subtitles are 12 lines per screen. The font with borders / outline MUST fit in a 60 pixel high bounding box. In practice, the max is about a 42 point font
	config.subtitles.subtitle_fontsize = ConfigSelection(choices=["%d" % x for x in range(20, 43, 2)], default="30")
	config.subtitles.showbackground = ConfigYesNo(default = False)

	subtitle_delay_choicelist = []
	for i in range(-900000, 1845000, 45000):
		if i == 0:
			subtitle_delay_choicelist.append(("0", _("No delay")))
		else:
			subtitle_delay_choicelist.append((str(i), "%2.1f sec" % (i / 90000.)))
	config.subtitles.subtitle_noPTSrecordingdelay = ConfigSelection(default="0", choices=subtitle_delay_choicelist)

	config.subtitles.dvb_subtitles_yellow = ConfigYesNo(default=False)
	config.subtitles.dvb_subtitles_original_position = ConfigSelection(default="0", choices=[("0", _("Original")), ("1", _("Fixed")), ("2", _("Relative"))])
	config.subtitles.subtitle_position = ConfigSelection(default="50", choices=["0", "10", "20", "30", "40", "50", "60", "70", "80", "90", "100", "150", "200", "250", "300", "350", "400", "450"])
	config.subtitles.dvb_subtitles_centered = ConfigYesNo(default = False)
	config.subtitles.subtitle_bad_timing_delay = ConfigSelection(default="0", choices=subtitle_delay_choicelist)
	config.subtitles.dvb_subtitles_backtrans = ConfigSelection(default="0", choices=[
		("0", _("No transparency")),
		("25", "10%"),
		("50", "20%"),
		("75", "30%"),
		("100", "40%"),
		("125", "50%"),
		("150", "60%"),
		("175", "70%"),
		("200", "80%"),
		("225", "90%"),
		("255", _("Full transparency"))])
	config.subtitles.pango_subtitle_colors = ConfigSelection(default="1", choices=[
		("0", _("alternative")),
		("1", _("white")),
		("2", _("yellow"))])
	config.subtitles.pango_subtitle_fontswitch = ConfigYesNo(default = True)
	config.subtitles.pango_subtitles_delay = ConfigSelection(default="0", choices=subtitle_delay_choicelist)
	config.subtitles.pango_subtitles_fps = ConfigSelection(default="1", choices=[
		("1", _("Original")),
		("23976", _("23.976")),
		("24000", _("24")),
		("25000", _("25")),
		("29970", _("29.97")),
		("30000", _("30"))])
	config.subtitles.pango_autoturnon = ConfigYesNo(default=True)

	config.subtitles.hide_teletext_undetermined_list = ConfigYesNo(default=False)
	config.subtitles.hide_teletext_undetermined_cycle = ConfigYesNo(default=True)

	config.autolanguage = ConfigSubsection()
	# Language codes are always lowercase; 3 letter codes should appear before 2 letter codes
	audio_language_choices = [
		("eng en", _("English")),
		("aus", _("Audio Description")),  # hack to deal with Australian broadcasters AD tracks
		("---", _("None")),
		("ara ar", _("Arabic")),
		("eus baq eu", _("Basque")),
		("bul bg", _("Bulgarian")),
		("zho chi zh", _("Chinese")),
		("hrv hr", _("Croatian")),
		("ces cze cs", _("Czech")),
		("dan da", _("Danish")),
		("nld dut nl", _("Dutch")),
		("ekk est et", _("Estonian")),
		("fin fi", _("Finnish")),
		("fra fre fr", _("French")),
		("deu ger de", _("German")),
		("ell gre el", _("Greek")),
		("heb he", _("Hebrew")),
		("hun hu", _("Hungarian")),
		("ita it", _("Italian")),
		("jpn ja", _("Japanese")),
		("kor ko", _("Korean")),
		("lav lvs lv", _("Latvian")),
		("lit lt", _("Lithuanian")),
		("ltz lb", _("Luxembourgish")),
		("nor no", _("Norwegian")),
		("pol pl", _("Polish")),
		("por pt", _("Portuguese")),
		("fas per pes fa", _("Persian")),
		("ron rum ro", _("Romanian")),
		("rus ru", _("Russian")),
		("srp sr", _("Serbian")),
		("slk slo", _("Slovak")),
		("slv sl", _("Slovenian")),
		("spa es", _("Spanish")),
		("swe sv", _("Swedish")),
		("tha th", _("Thai")),
		("tur tr", _("Turkish")),
		("ukr uk", _("Ukrainian")),
		("vie vi", _("Vietnamese")),
		("und", _("Undetermined"))
		]

	def setEpgLanguage(configElement):
		eServiceEvent.setEPGLanguage(configElement.value)

	config.autolanguage.audio_epglanguage = ConfigSelection(audio_language_choices[:-1], default="---")
	config.autolanguage.audio_epglanguage.addNotifier(setEpgLanguage)

	def setEpgLanguageAlternative(configElement):
		eServiceEvent.setEPGLanguageAlternative(configElement.value)

	config.autolanguage.audio_epglanguage_alternative = ConfigSelection(audio_language_choices[:-1], default="---")
	config.autolanguage.audio_epglanguage_alternative.addNotifier(setEpgLanguageAlternative)

	config.autolanguage.audio_autoselect1 = ConfigSelection(choices=audio_language_choices, default="eng en")
	config.autolanguage.audio_autoselect2 = ConfigSelection(choices=audio_language_choices, default="---")
	config.autolanguage.audio_autoselect3 = ConfigSelection(choices=audio_language_choices, default="---")
	config.autolanguage.audio_autoselect4 = ConfigSelection(choices=audio_language_choices, default="---")
	config.autolanguage.audio_defaultac3 = ConfigYesNo(default=True)
	config.autolanguage.audio_defaultddp = ConfigYesNo(default=False)
	config.autolanguage.audio_usecache = ConfigYesNo(default=False)

	subtitle_language_choices = audio_language_choices[:1] + audio_language_choices[2:]
	config.autolanguage.subtitle_autoselect1 = ConfigSelection(choices=subtitle_language_choices, default="---")
	config.autolanguage.subtitle_autoselect2 = ConfigSelection(choices=subtitle_language_choices, default="---")
	config.autolanguage.subtitle_autoselect3 = ConfigSelection(choices=subtitle_language_choices, default="---")
	config.autolanguage.subtitle_autoselect4 = ConfigSelection(choices=subtitle_language_choices, default="---")
	config.autolanguage.subtitle_hearingimpaired = ConfigYesNo(default=False)
	config.autolanguage.subtitle_defaultimpaired = ConfigYesNo(default=False)
	config.autolanguage.subtitle_defaultdvb = ConfigYesNo(default=False)
	config.autolanguage.subtitle_usecache = ConfigYesNo(default=True)
	config.autolanguage.equal_languages = ConfigSelection(default="15", choices=[
		("0", _("None")), ("1", "1"), ("2", "2"), ("3", "1,2"),
		("4", "3"), ("5", "1,3"), ("6", "2,3"), ("7", "1,2,3"),
		("8", "4"), ("9", "1,4"), ("10", "2,4"), ("11", "1,2,4"),
		("12", "3,4"), ("13", "1,3,4"), ("14", "2,3,4"), ("15", _("All"))])

	config.logmanager = ConfigSubsection()
	config.logmanager.showinextensions = ConfigYesNo(default=False)
	config.logmanager.path = ConfigText(default="/")
	config.logmanager.sentfiles = ConfigLocations(default='')

	config.vixsettings = ConfigSubsection()
	config.vixsettings.Subservice = ConfigYesNo(default=True)
	config.vixsettings.ColouredButtons = ConfigYesNo(default=False)
	config.vixsettings.InfoBarEpg_mode = ConfigSelection(default="0", choices=[
		("0", _("as plugin in extended bar")),
		("1", _("with long OK press")),
		("2", _("with exit button")),
		("3", _("with left/right buttons"))])

	config.epgselection = ConfigSubsection()
	config.epgselection.sort = ConfigSelection(default="0", choices=[("0", _("Time")), ("1", _("Alphanumeric"))])
	config.epgselection.overjump = ConfigYesNo(default=False)
	config.epgselection.infobar_type_mode = ConfigSelection(default="graphics", choices=[("text", _("Text Multi EPG")), ("graphics", _("Graphics Multi EPG")), ("single", _("Single EPG"))])
	if SystemInfo.get("NumVideoDecoders", 1) > 1:
		config.epgselection.infobar_preview_mode = ConfigSelection(default="1", choices=[("0", _("Disabled")), ("1", _("Full screen")), ("2", _("PiP"))])
	else:
		config.epgselection.infobar_preview_mode = ConfigSelection(default="1", choices=[("0", _("Disabled")), ("1", _("Full screen"))])
	config.epgselection.infobar_ok = ConfigSelection(default="Zap", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.infobar_oklong = ConfigSelection(default="Zap + Exit", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.infobar_itemsperpage = ConfigSelectionNumber(default=2, stepwidth=1, min=1, max=4, wraparound=True)
	config.epgselection.infobar_roundto = ConfigSelection(default="15", choices=[("15", _("%d minutes") % 15), ("30", _("%d minutes") % 30), ("60", _("%d minutes") % 60)])
	config.epgselection.infobar_prevtime = ConfigClock(default=time())
	config.epgselection.infobar_prevtimeperiod = ConfigSelection(default="180", choices=[("60", _("%d minutes") % 60), ("90", _("%d minutes") % 90), ("120", _("%d minutes") % 120), ("150", _("%d minutes") % 150), ("180", _("%d minutes") % 180), ("210", _("%d minutes") % 210), ("240", _("%d minutes") % 240), ("270", _("%d minutes") % 270), ("300", _("%d minutes") % 300)])
	config.epgselection.infobar_visiblehistory = ConfigSelection(default="0", choices=[("0", _("None")), ("25", _("Minimal")), ("50", _("Balanced")), ("75", _("Maximum"))])
	config.epgselection.infobar_primetimehour = ConfigSelectionNumber(default=20, stepwidth=1, min=00, max=23, wraparound=True)
	config.epgselection.infobar_primetimemins = ConfigSelectionNumber(default=00, stepwidth=1, min=00, max=59, wraparound=True)
	config.epgselection.infobar_servicetitle_mode = ConfigSelection(default="picon+servicename", choices=[("servicename", _("Service Name")), ("picon", _("Picon")), ("picon+servicename", _("Picon and Service Name"))])
	config.epgselection.infobar_servfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.infobar_eventfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.infobar_timelinefs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.infobar_timeline24h = ConfigYesNo(default=True)
	config.epgselection.infobar_servicewidth = ConfigSelectionNumber(default=200, stepwidth=1, min=70, max=500, wraparound=True)
	config.epgselection.infobar_piconwidth = ConfigSelectionNumber(default=100, stepwidth=1, min=50, max=500, wraparound=True)
	config.epgselection.infobar_infowidth = ConfigSelectionNumber(default=50, stepwidth=25, min=0, max=150, wraparound=True)
	config.epgselection.enhanced_preview_mode = ConfigYesNo(default=True)
	config.epgselection.enhanced_picon = ConfigYesNo(default=True)
	config.epgselection.enhanced_ok = ConfigSelection(default="Zap", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.enhanced_oklong = ConfigSelection(default="Zap + Exit", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.enhanced_eventfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.enhanced_itemsperpage = ConfigSelectionNumber(default = 18, stepwidth = 1, min = 1, max = 40, wraparound = True)
	config.epgselection.multi_showbouquet = ConfigYesNo(default=False)
	config.epgselection.multi_preview_mode = ConfigYesNo(default=True)
	config.epgselection.multi_ok = ConfigSelection(default="Zap", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.multi_oklong = ConfigSelection(default="Zap + Exit", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.multi_eventfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.multi_itemsperpage = ConfigSelectionNumber(default=18, stepwidth=1, min=12, max=40, wraparound=True)
	config.epgselection.graph_showbouquet = ConfigYesNo(default=False)
	config.epgselection.graph_preview_mode = ConfigYesNo(default=True)
	config.epgselection.graph_type_mode = ConfigSelection(default="graphics", choices=[("graphics", _("Graphics")), ("text", _("Text"))])
	config.epgselection.graph_highlight_current_events = ConfigYesNo(default=True)
	config.epgselection.graph_ok = ConfigSelection(default="Zap", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.graph_oklong = ConfigSelection(default="Zap + Exit", choices=[("Zap", _("Zap")), ("Zap + Exit", _("Zap + Exit"))])
	config.epgselection.graph_info = ConfigSelection(default="Channel Info", choices=[("Channel Info", _("Channel Info")), ("Single EPG", _("Single EPG"))])
	config.epgselection.graph_infolong = ConfigSelection(default="Single EPG", choices=[("Channel Info", _("Channel Info")), ("Single EPG", _("Single EPG"))])
	config.epgselection.graph_roundto = ConfigSelection(default="15", choices=[("15", _("%d minutes") % 15), ("30", _("%d minutes") % 30), ("60", _("%d minutes") % 60)])
	config.epgselection.graph_prevtime = ConfigClock(default=time())
	config.epgselection.graph_prevtimeperiod = ConfigSelection(default="180", choices=[("60", _("%d minutes") % 60), ("90", _("%d minutes") % 90), ("120", _("%d minutes") % 120), ("150", _("%d minutes") % 150), ("180", _("%d minutes") % 180), ("210", _("%d minutes") % 210), ("240", _("%d minutes") % 240), ("270", _("%d minutes") % 270), ("300", _("%d minutes") % 300)])
	config.epgselection.graph_visiblehistory = ConfigSelection(default="0", choices=[("0", _("None")), ("25", _("Minimal")), ("50", _("Balanced")), ("75", _("Maximum"))])
	config.epgselection.graph_primetimehour = ConfigSelectionNumber(default=20, stepwidth=1, min=00, max=23, wraparound=True)
	config.epgselection.graph_primetimemins = ConfigSelectionNumber(default=00, stepwidth=1, min=00, max=59, wraparound=True)
	config.epgselection.graph_servicetitle_mode = ConfigSelection(default = "picon+servicename", choices = [("servicename", _("Service Name")), ("picon", _("Picon")), ("picon+servicename", _("Picon and Service Name")), ("servicenumber+servicename", _("Service Number and Service Name")), ("servicenumber+picon+servicename", _("Service Number, Picon and Service Name"))])
	config.epgselection.graph_channel1 = ConfigYesNo(default=False)
	possibleAlignmentChoices = [
			( str(RT_HALIGN_LEFT   | RT_VALIGN_TOP          ) , _("left")),
			( str(RT_HALIGN_CENTER | RT_VALIGN_TOP          ) , _("centered")),
			( str(RT_HALIGN_RIGHT  | RT_VALIGN_TOP          ) , _("right")),
			( str(RT_HALIGN_LEFT   | RT_VALIGN_TOP | RT_WRAP) , _("left, wrapped")),
			( str(RT_HALIGN_CENTER | RT_VALIGN_TOP | RT_WRAP) , _("centered, wrapped")),
			( str(RT_HALIGN_RIGHT  | RT_VALIGN_TOP | RT_WRAP) , _("right, wrapped"))]
	config.epgselection.graph_servicename_alignment = ConfigSelection(default = possibleAlignmentChoices[0][0], choices = possibleAlignmentChoices)
	config.epgselection.graph_servicenumber_alignment = ConfigSelection(default = possibleAlignmentChoices[0][0], choices = possibleAlignmentChoices)
	config.epgselection.graph_event_alignment = ConfigSelection(default = possibleAlignmentChoices[0][0], choices = possibleAlignmentChoices)
	config.epgselection.graph_timelinedate_alignment = ConfigSelection(default = possibleAlignmentChoices[0][0], choices = possibleAlignmentChoices)
	config.epgselection.graph_servfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.graph_eventfs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.graph_timelinefs = ConfigSelectionNumber(default=0, stepwidth=1, min=-8, max=10, wraparound=True)
	config.epgselection.graph_timeline24h = ConfigYesNo(default=True)
	config.epgselection.graph_itemsperpage = ConfigSelectionNumber(default=8, stepwidth=1, min=3, max=20, wraparound=True)
	config.epgselection.graph_pig = ConfigYesNo(default=True)
	config.epgselection.graph_heightswitch = NoSave(ConfigYesNo(default=False))
	config.epgselection.graph_servicewidth = ConfigSelectionNumber(default=250, stepwidth=1, min=70, max=500, wraparound=True)
	config.epgselection.graph_piconwidth = ConfigSelectionNumber(default=100, stepwidth=1, min=50, max=500, wraparound=True)
	config.epgselection.graph_infowidth = ConfigSelectionNumber(default=50, stepwidth=25, min=0, max=150, wraparound=True)
	config.epgselection.graph_rec_icon_height = ConfigSelection(choices = [("bottom",_("bottom")),("top", _("top")), ("middle", _("middle")),  ("hide", _("hide"))], default = "bottom")

	if not os.path.exists('/usr/emu_scripts/'):
		os.mkdir('/usr/emu_scripts/', 0755)
	softcams = os.listdir('/usr/emu_scripts/')
	config.oscaminfo = ConfigSubsection()
	config.oscaminfo.showInExtensions = ConfigYesNo(default=False)
	config.oscaminfo.userdatafromconf = ConfigYesNo(default = True)
	config.oscaminfo.autoupdate = ConfigYesNo(default=False)
	config.oscaminfo.username = ConfigText(default="username", fixed_size=False, visible_width=12)
	config.oscaminfo.password = ConfigPassword(default="password", fixed_size=False)
	config.oscaminfo.ip = ConfigIP(default=[127, 0, 0, 1], auto_jump=True)
	config.oscaminfo.port = ConfigInteger(default=16002, limits=(0, 65536))
	config.oscaminfo.intervall = ConfigSelectionNumber(default=10, min=1, max=600, stepwidth=1, wraparound=True)
	SystemInfo["OScamInstalled"] = False

	config.cccaminfo = ConfigSubsection()
	config.cccaminfo.showInExtensions = ConfigYesNo(default=False)
	config.cccaminfo.serverNameLength = ConfigSelectionNumber(default=22, min=10, max=100, stepwidth=1, wraparound=True)
	config.cccaminfo.name = ConfigText(default="Profile", fixed_size=False)
	config.cccaminfo.ip = ConfigText(default="192.168.2.12", fixed_size=False)
	config.cccaminfo.username = ConfigText(default="", fixed_size=False)
	config.cccaminfo.password = ConfigText(default="", fixed_size=False)
	config.cccaminfo.port = ConfigInteger(default=16001, limits=(1, 65535))
	config.cccaminfo.profile = ConfigText(default="", fixed_size=False)
	config.cccaminfo.ecmInfoEnabled = ConfigYesNo(default=True)
	config.cccaminfo.ecmInfoTime = ConfigSelectionNumber(default=5, min=1, max=10, stepwidth=1, wraparound=True)
	config.cccaminfo.ecmInfoForceHide = ConfigYesNo(default=True)
	config.cccaminfo.ecmInfoPositionX = ConfigInteger(default=50)
	config.cccaminfo.ecmInfoPositionY = ConfigInteger(default=50)
	config.cccaminfo.blacklist = ConfigText(default="/media/cf/CCcamInfo.blacklisted", fixed_size=False)
	config.cccaminfo.profiles = ConfigText(default="/media/cf/CCcamInfo.profiles", fixed_size=False)
	SystemInfo["CCcamInstalled"] = False
	for softcam in softcams:
		if softcam.lower().startswith('cccam'):
			config.cccaminfo.showInExtensions = ConfigYesNo(default=True)
			SystemInfo["CCcamInstalled"] = True
		elif softcam.lower().startswith('oscam'):
			config.oscaminfo.showInExtensions = ConfigYesNo(default=True)
			SystemInfo["OScamInstalled"] = True

	config.streaming = ConfigSubsection()
	config.streaming.stream_ecm = ConfigYesNo(default=False)
	config.streaming.descramble = ConfigYesNo(default=True)
	config.streaming.descramble_client = ConfigYesNo(default = False)
	config.streaming.stream_eit = ConfigYesNo(default=True)
	config.streaming.stream_ait = ConfigYesNo(default=True)
	config.streaming.authentication = ConfigYesNo(default=False)

	config.pluginbrowser = ConfigSubsection()
	config.pluginbrowser.po = ConfigYesNo(default=False)
	config.pluginbrowser.src = ConfigYesNo(default=False)
	
	config.mediaplayer = ConfigSubsection()
	config.mediaplayer.useAlternateUserAgent = ConfigYesNo(default=False)
	config.mediaplayer.alternateUserAgent = ConfigText(default="")

def updateChoices(sel, choices):
	if choices:
		defval = None
		val = int(sel.value)
		if val not in choices:
			tmp = choices[:]
			tmp.reverse()
			for x in tmp:
				if x < val:
					defval = str(x)
					break
		sel.setChoices(map(str, choices), defval)

def preferredPath(path):
	if config.usage.setup_level.index < 2 or path == "<default>":
		return None  # config.usage.default_path.value, but delay lookup until usage
	elif path == "<current>":
		return config.movielist.last_videodir.value
	elif path == "<timer>":
		return config.movielist.last_timer_videodir.value
	else:
		return path

def preferredTimerPath():
	return preferredPath(config.usage.timer_path.value)

def preferredInstantRecordPath():
	return preferredPath(config.usage.instantrec_path.value)

def defaultMoviePath():
	return defaultRecordingLocation(config.usage.default_path.value)
