"""
A Python interface for the PV_Live web API from Sheffield Solar.

- Jamie Taylor <jamie.taylor@sheffield.ac.uk>
- Ethan Jones <ejones18@sheffield.ac.uk>
- First Authored: 2018-06-04
- Updated: 2020-10-20 to return Pandas dataframe object
"""

from __future__ import print_function
import json
from datetime import datetime, timedelta, date, time
from time import sleep
import pytz
import requests
import pandas as pd 

class PVLiveException(Exception):
    """An Exception specific to the PVLive class."""
    def __init__(self, msg):
        try:
            caller_file = inspect.stack()[2][1]
        except:
            import os
            caller_file = os.path.basename(__file__)
        self.msg = "%s (in '%s')" % (msg, caller_file)
    def __str__(self):
        return self.msg

class PVLive:
    """
    Interface with the PV_Live web API.
    
    Parameters
    ----------
    `retries` : int
        Optionally specify the number of retries to use should the API respond with anything
        other than status code 200. Exponential back-off applies inbetween retries.
    """
    def __init__(self, retries=3):
        self.base_url = "https://api0.solar.sheffield.ac.uk/pvlive/v2/pes"
        self.max_range = {"national": timedelta(days=365), "regional": timedelta(days=30)}
        self.retries = retries

    def latest(self, pes_id=0, data_frame=False, extra_fields=""):
        """
        Get the latest PV_Live generation result from the API.

        Parameters
        ----------
        `pes_id` : int
            The numerical ID of the PES region of interest. Defaults to 0 (i.e. national).
        data_frame` : boolean
            Boolean indicator whether to return data as a dataframe or not.
        `extra_fields` : string
            Comma-separated string listing of the names of any extra fields required.
        Returns
        -------
        tuple
            Tuple containing the pes_id, datetime_GMT and generation_MW fields of the latest
            PV_Live result, plus any extra_fields in the order specified.
            
            OR
            
        dataframe
            The row of the dataframe contains the columns pes_id, datetime_GMT and generation_MW fields of a PV_Live
            result, plus any extra_fields in the order specified.
        Notes
        -----
        For list of optional *extra_fields*, see `PV_Live API Docs
        <https://www.solar.sheffield.ac.uk/pvlive/api/>`_.
        """
        if not isinstance(pes_id, int) or pes_id not in range(0, 328):
            raise PVLiveException("The pes_id must be an integer between 0 and 327 (inclusive).")
        if not isinstance(extra_fields, str):
            raise PVLiveException("The extra_fields must be a comma-separated string.")
        params = self._compile_params(extra_fields)
        response = self._query_api(pes_id, params)
        if response["data"]:
            if data_frame:
                return self.convert_tuple_to_df(response["data"][0], response['meta'])
            return tuple(response["data"][0])
        return (None, None, None)

    def at_time(self, dt, pes_id=0, data_frame=False, extra_fields=""):
        """
        Get the PV_Live generation result for a given time from the API.

        Parameters
        ----------
        `dt` : datetime
            A timezone-aware datetime object. Will be corrected to the END of the half hour in which
            *dt* falls, since Sheffield Solar use end of interval as convention.
        `pes_id` : int
            The numerical ID of the PES region of interest. Defaults to 0 (i.e. national).
        `data_frame` : boolean
            Boolean indicator whether to return data as a dataframe or not.
        `extra_fields` : string
            Comma-separated string listing of the names of any extra fields required.
        Returns
        -------
        tuple
            Tuple containing the pes_id, datetime_GMT and generation_MW fields of the PV_Live
            result, plus any extra_fields in the order specified.
            
            OR
            
        dataframe
            The row of the dataframe contains the columns pes_id, datetime_GMT and generation_MW fields of a PV_Live
            result, plus any extra_fields in the order specified.
        Notes
        -----
        For list of optional *extra_fields*, see `PV_Live API Docs
        <https://www.solar.sheffield.ac.uk/pvlive/api/>`_.
        """
        if not isinstance(dt, datetime) or dt.tzinfo is None:
            PVLiveException("The dt must be a timezone-aware Python datetime object.")
        dt = self._nearest_hh(dt)
        params = self._compile_params(extra_fields, dt)
        response = self._query_api(pes_id, params)
        if response["data"]:
            if data_frame:
                return self.convert_tuple_to_df(response["data"][0], response['meta'])
            return tuple(response["data"][0])
        return (None, None, None)

    def between(self, start, end, pes_id=0, data_frame=False, extra_fields=""):
        """
        Get the PV_Live generation result for a given time interval from the API.

        Parameters
        ----------
        `start` : datetime
            A timezone-aware datetime object. Will be corrected to the END of the half hour in which
            *start* falls, since Sheffield Solar use end of interval as convention.
        `end` : datetime
            A timezone-aware datetime object. Will be corrected to the END of the half hour in which
            *end* falls, since Sheffield Solar use end of interval as convention.
        `pes_id` : int
            The numerical ID of the PES region of interest. Defaults to 0 (i.e. national).
        `data_frame` : boolean
            Boolean indicator whether to return data as a dataframe or not.
        `extra_fields` : string
            Comma-separated string listing of the names of any extra fields required.
        Returns
        -------
        list
            Each element of the outter list is a list containing the pes_id, datetime_GMT and
            generation_MW fields of a PV_Live result, plus any extra_fields in the order specified.
            
            OR
            
        dataframe
            Each row of the dataframe contains the columns pes_id, datetime_GMT and generation_MW fields of a PV_Live
            result, plus any extra_fields in the order specified.
        Notes
        -----
        For list of optional *extra_fields*, see `PV_Live API Docs
        <https://www.solar.sheffield.ac.uk/pvlive/api/>`_.
        """
        type_check = not (isinstance(start, datetime) and isinstance(end, datetime))
        tz_check = start.tzinfo is None or end.tzinfo is None
        if type_check or tz_check:
            PVLiveException("Start and end must be timezone-aware Python datetime objects.")
        start = self._nearest_hh(start)
        end = self._nearest_hh(end)
        data = []
        request_start = start
        max_range = self.max_range["national"] if pes_id == 0 else self.max_range["regional"]
        while request_start < end:
            request_end = min(end, request_start + max_range)
            params = self._compile_params(extra_fields, request_start, request_end)
            response = self._query_api(pes_id, params)
            data += response["data"]
            request_start += max_range + timedelta(minutes=30)
        if data_frame:
            columns = response['meta']
            data = pd.DataFrame(data, columns=columns)
        return data

    def day_peak(self, d, pes_id=0, data_frame=False, extra_fields=""):
        """
        Get the peak PV_Live generation result for a given day from the API.

        Parameters
        ----------
        `d` : date
            The day of interest as a date object.
        `pes_id` : int
            The numerical ID of the PES region of interest. Defaults to 0 (i.e. national).
        `data_frame` : boolean
            Boolean indicator whether to return data as a dataframe or not.
        `extra_fields` : string
            Comma-separated string listing of the names of any extra fields required.
        Returns
        -------
        tuple
            Tuple containing the pes_id, datetime_GMT and generation_MW fields of the latest
            PV_Live result, plus any extra_fields in the order specified.
            
            OR
            
        dataframe
            The row of the dataframe contains the columns pes_id, datetime_GMT and generation_MW fields of a PV_Live
            result, plus any extra_fields in the order specified.
        Notes
        -----
        For list of optional *extra_fields*, see `PV_Live API Docs
        <https://www.solar.sheffield.ac.uk/pvlive/api/>`_.
        """
        if not isinstance(d, date):
            PVLiveException("The d must be a Python date object.")
        start = datetime.combine(d, time(0, 30, tzinfo=pytz.UTC))
        end = start + timedelta(days=1) - timedelta(minutes=30)
        params = self._compile_params(extra_fields, start, end)
        response = self._query_api(pes_id, params)
        if response["data"]:
            gens = [x[2] if x[2] is not None else -1e308 for x in response["data"]]
            index_max = max(range(len(gens)), key=gens.__getitem__)
            if data_frame:
                return self.convert_tuple_to_df(response["data"][index_max], response['meta'])
            return tuple(response["data"][index_max])
        return (None, None, None)

    def day_energy(self, d, pes_id=0):
        """
        Get the cumulative PV generation for a given day from the API.

        Parameters
        ----------
        `d` : date
            The day of interest as a date object.
        `pes_id` : int
            The numerical ID of the PES region of interest. Defaults to 0 (i.e. national).
        Returns
        -------
        float
            The cumulative PV generation on the given day in MWh.
        Notes
        -----
        For list of optional *extra_fields*, see `PV_Live API Docs
        <https://www.solar.sheffield.ac.uk/pvlive/api/>`_.
        """
        if not isinstance(d, date):
            PVLiveException("The d must be a Python date object.")
        start = datetime.combine(d, time(0, 30, tzinfo=pytz.UTC))
        end = start + timedelta(days=1) - timedelta(minutes=30)
        params = self._compile_params("", start, end)
        response = self._query_api(pes_id, params)
        if response["data"]:
            pv_energy = sum([x[2] if x[2] is not None else 0 for x in response["data"]]) * 0.5
            return pv_energy
        return None

    def _compile_params(self, extra_fields="", start=None, end=None):
        """Compile parameters into a Python dict, formatting where necessary."""
        params = {}
        if extra_fields:
            params["extra_fields"] = extra_fields
        if start is not None:
            params["start"] = start.isoformat().replace('+00:00', 'Z')
        end = start if (start is not None and end is None) else end
        if end is not None:
            params["end"] = end.isoformat().replace('+00:00', 'Z')
        return params

    def _query_api(self, pes_id, params):
        """Query the API with some REST parameters."""
        url = self._build_url(pes_id, params)
        # print(url)
        return self._fetch_url(url)

    def convert_tuple_to_df(self, data, columns):
        """Converts a tuple of values to a data-frame object."""
        df = pd.DataFrame([data], columns=columns)
        return df

    def _build_url(self, pes_id, params):
        """Construct the appropriate URL for a given set of parameters."""
        base_url = "{}/{}".format(self.base_url, pes_id)
        url = base_url + "?" + "&".join(["{}={}".format(k, params[k]) for k in params])
        return url

    def _fetch_url(self, url):
        """Fetch the URL with GET request."""
        success = False
        try_counter = 0
        delay = 1
        while not success and try_counter < self.retries + 1:
            # print(try_counter)
            try_counter += 1
            try:
                page = requests.get(url)
                page.raise_for_status()
                success = True
            except requests.exceptions.HTTPError:
                sleep(delay)
                delay *= 2
                continue
            except:
                raise
        if not success:
            raise PVLiveException("Error communicating with the PV_Live API.")
        try:
            return json.loads(page.text)
        except:
            raise PVLiveException("Error communicating with the PV_Live API.")

    def _nearest_hh(self, dt):
        """Round a given datetime object up to the nearest half hour."""
        if not(dt.minute % 30 == 0 and dt.second == 0 and dt.microsecond == 0):
            dt = dt - timedelta(minutes=dt.minute%30, seconds=dt.second) + timedelta(minutes=30)
        return dt

def main():
    """Demo the module's capabilities."""
    pvlive = PVLive()
    print("\nLatest: ")
    print(pvlive.latest())
    print("\nAs Pandas Dataframe: ")
    print(pvlive.latest(0, True))
    print("\nAt 2018-06-03 12:00: ")
    print(pvlive.at_time(datetime(2018, 6, 3, 12, 0, tzinfo=pytz.utc)))
    print("\nAt 2018-06-03 12:35: ")
    print(pvlive.at_time(datetime(2018, 6, 3, 12, 35, tzinfo=pytz.utc)))
    print("\nAs Pandas Dataframe object: ")
    print(pvlive.at_time(datetime(2018, 6, 3, 12, 35, tzinfo=pytz.utc), 0, True))
    print("\nBetween 2018-06-03 12:20 and 2018-06-03 14:00 as a DataFrame object: ")
    print(pvlive.between(datetime(2018, 6, 3, 12, 20, tzinfo=pytz.utc),
                         datetime(2018, 6, 3, 14, 00, tzinfo=pytz.utc), 0, True, "ucl_mw,stats_error"))
    print("\nBetween 2018-07-02 12:20 and 2018-07-03 14:00: ")
    print(pvlive.between(datetime(2018, 7, 3, 12, 20, tzinfo=pytz.utc),
                         datetime(2018, 7, 3, 14, 00, tzinfo=pytz.utc)))
    print("\nPeak on 2018-06-03 as Pandas Dataframe object: ")
    print(pvlive.day_peak(date(2018, 6, 3), 0, True, "ucl_mw"))
    print("\nCumulative generation on 2018-06-03: ")
    print(pvlive.day_energy(date(2018, 6, 3)))

if __name__ == "__main__":
    main()
