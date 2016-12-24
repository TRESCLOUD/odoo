# -*- coding: utf-8 -*-
##############################################################################
#    Copyright (C) 2016 TRESCLOUD Cia. Ltda. (<http://www.trescloud.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

"""
timezone module - methods intended to provide control of date and time zone
"""

from datetime import datetime

def offset_format_timestamp(src_tstamp_str, src_format, dst_format, server_to_client=True, ignore_unparsable_time=True, context=None):
    """
    Convert a source timestamp string into a destination timestamp string, attempting to apply the
    correct offset if both the server and local timezone are recognized, or no
    offset at all if they aren"t or if tz_offset is false (i.e. assuming they are both in the same TZ).

    @param src_tstamp_str: the str value containing the timestamp.
    @param src_format: the format to use when parsing the local timestamp.
    @param dst_format: the format to use when formatting the resulting timestamp.
    @param server_to_client: specify timezone offset direction (server=src and client=dest if True, or client=src and server=dest if False)
    @param ignore_unparsable_time: if True, return False if src_tstamp_str cannot be parsed
                                   using src_format or formatted using dst_format.

    @return: destination formatted timestamp, expressed in the destination timezone if possible
            and if tz_offset is true, or src_tstamp_str if timezone offset could not be determined.
    """
    if not src_tstamp_str:
        return False

    res = src_tstamp_str
    if src_format and dst_format:
        try:
            # dt_value needs to be a datetime.datetime object (so no time.struct_time or mx.DateTime.DateTime here!)
            dt_value = datetime.strptime(src_tstamp_str,src_format)
            if context.get("tz",False):
                try:
                    import pytz
                    if server_to_client:
                        src_tz = pytz.timezone("UTC")
                        dst_tz = pytz.timezone(context["tz"])
                    else:
                        src_tz = pytz.timezone(context["tz"])
                        dst_tz = pytz.timezone("UTC")
                    src_dt = src_tz.localize(dt_value, is_dst=True)
                    dt_value = src_dt.astimezone(dst_tz)
                except Exception,e:
                    pass
            res = dt_value.strftime(dst_format)
        except Exception,e:
            # Normal ways to end up here are if strptime or strftime failed
            if not ignore_unparsable_time:
                return False
            pass
    return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
