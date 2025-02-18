# kate: replace-tabs on; indent-width 4; remove-trailing-spaces all; show-tabs on; newline-at-eof on;
# -*- coding:utf-8 -*-

'''
Copyright 2014-2021 Peter Urbanec

SPDX-License-Identifier: GPL-3.0-or-later

For alternate licensing options contact enigma.licensing (at) urbanec.net

This file is part of IceTV Plugin for enigma2.

IceTV Plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

IceTV Plugin is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with IceTV Plugin.  If not, see <https://www.gnu.org/licenses/>.

'''

from __future__ import print_function, division

from enigma import eEPGCache
from boxbranding import getMachineBrand, getMachineName
from Components.config import config, ConfigSubsection, ConfigNumber, ConfigText, \
    ConfigPassword, ConfigSelection, NoSave, configfile, ConfigYesNo, \
    ConfigSelectionNumber
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_PLUGINS
from Tools.LoadPixmap import LoadPixmap
import os.path

def getIceTVDeviceType():
    return {
        ("Beyonwiz", "T2"): 31,
        ("Beyonwiz", "T3"): 22,
        ("Beyonwiz", "T4"): 30,
        ("Beyonwiz", "U4"): 36,
        ("Beyonwiz", "V2"): 38,
    }.get((getMachineBrand(), getMachineName()), 22)


config.plugins.icetv = ConfigSubsection()

config.plugins.icetv.server = ConfigSubsection()
config.plugins.icetv.server.name = ConfigText(default="api.icetv.com.au")

config.plugins.icetv.member = ConfigSubsection()
config.plugins.icetv.member.email_address = ConfigText(show_help=False, fixed_size=False)
config.plugins.icetv.member.token = ConfigText()
config.plugins.icetv.member.id = ConfigNumber()
config.plugins.icetv.member.region_id = ConfigNumber()
config.plugins.icetv.member.country = ConfigText(default="AUS")

config.plugins.icetv.member.password = NoSave(ConfigPassword(censor="●", show_help=False, fixed_size=False))

config.plugins.icetv.device = ConfigSubsection()
config.plugins.icetv.device.label = ConfigText(default="%s %s" % (getMachineBrand(), getMachineName()), show_help=False)
config.plugins.icetv.device.id = ConfigNumber()
config.plugins.icetv.device.type_id = ConfigNumber(default=getIceTVDeviceType())

config.plugins.icetv.last_update_time = ConfigNumber()
if config.plugins.icetv.last_update_time.value != 0:
    config.plugins.icetv.last_update_time.value = 0
    config.plugins.icetv.last_update_time.save()
    configfile.save()
config.plugins.icetv.last_update_time.disableSave()

config.plugins.icetv.enable_epg = ConfigYesNo(default=False)
config.plugins.icetv.send_logs = ConfigYesNo(default=False)
config.plugins.icetv.configured = ConfigYesNo(default=False)

minute = 60
hour = minute * 60

checktimes = [
    ("%d" % int(minute * 2), _("2 minutes")),
    ("%d" % int(minute * 5), _("5 minutes")),
    ("%d" % int(minute * 10), _("10 minutes")),
    ("%d" % int(minute * 15), _("15 minutes")),
    ("%d" % int(minute * 30), _("30 minutes")),
    ("%d" % int(hour), _("1 hour")),
    ("%d" % int(hour * 2), _("2 hours")),
    ("%d" % int(hour * 3), _("3 hours")),
    ("%d" % int(hour * 4), _("4 hours")),
    ("%d" % int(hour * 5), _("5 hours")),
    ("%d" % int(hour * 6), _("6 hours")),
    ("%d" % int(hour * 7), _("7 hours")),
    ("%d" % int(hour * 8), _("8 hours")),
    ("%d" % int(hour * 12), _("12 hours")),
    ("%d" % int(hour * 24), _("24 hours")),
]

config.plugins.icetv.refresh_interval = ConfigSelection(default="%d" % int(minute * 15), choices=checktimes)

# Fetch EPG in batches of channels no larger than this size.
# If set to 0, there is no upper limit to the dynamically-calculated
# batch size (other than the number of channels actually available)

config.plugins.icetv.max_batchsize = ConfigSelectionNumber(0, 50, 1, default=30)

def saveConfigFile():
    config.plugins.icetv.save()
    configfile.save()

def enableIceTV():
    setIceTVDefaults()
    epgcache = eEPGCache.getInstance()
    epgcache.setEpgSources(0)
    try:
        epgcache.clear()
    except AttributeError:
        epgcache.flushEPG()
    epgcache.save()
    saveConfigFile()

def disableIceTV():
    epgcache = eEPGCache.getInstance()
    epgcache.setEpgSources(0)
    try:
        epgcache.clear()
    except AttributeError:
        epgcache.flushEPG()
    epgcache.save()
    epgcache.setEpgSources(eEPGCache.NOWNEXT | eEPGCache.SCHEDULE | eEPGCache.SCHEDULE_OTHER)
    restoreDefaults()
    saveConfigFile()

def setIceTVDefaults():
    config.plugins.icetv.enable_epg.value = True
    config.plugins.icetv.last_update_time.value = 0
    config.epg.eit.value = False
    config.epg.save()
    config.usage.show_eit_nownext.value = False
    config.usage.show_eit_nownext.save()

def restoreDefaults():
    config.usage.show_eit_nownext.value = True
    config.usage.show_eit_nownext.save()
    config.epg.eit.value = True
    config.epg.save()
    config.plugins.icetv.enable_epg.value = False
    config.plugins.icetv.last_update_time.value = 0

def loadIceTVIcon(iconname):
    for scope, path in ((SCOPE_CURRENT_SKIN, "icons"), (SCOPE_PLUGINS, "SystemPlugins/IceTV/icons")):
        iconpixmap = LoadPixmap(resolveFilename(scope, os.path.join(path, iconname)))
        if iconpixmap:
            return iconpixmap
    return None
