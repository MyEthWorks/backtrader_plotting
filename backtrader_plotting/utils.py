from datetime import datetime
import logging
import math
from typing import Dict, Optional, List, Union

import backtrader as bt

import pandas as pd
import itertools


_logger = logging.getLogger(__name__)


def paramval2str(name, value):
    if value is None:  # catch None value early here!
        return str(value)
    elif name == "timeframe":
        return bt.TimeFrame.getname(value, 1)
    elif isinstance(value, float):
        return f"{value:.2f}"
    elif isinstance(value, (list,tuple)):
        return ','.join(value)
    elif isinstance(value, type):
        return value.__name__
    else:
        return str(value)


def get_nondefault_params(params: object) -> Dict[str, object]:
    return {key: params._get(key) for key in params._getkeys() if not params.isdefault(key)}


def get_params(params: bt.AutoInfoClass):
    return {key: params._get(key) for key in params._getkeys()}


def get_params_str(params: Optional[bt.AutoInfoClass]) -> str:
    user_params = get_nondefault_params(params)
    plabs = [f"{x}: {paramval2str(x, y)}" for x, y in user_params.items()]
    plabs = '/'.join(plabs)
    return plabs


def nanfilt(x: List) -> List:
    """filters all NaN values from a list"""
    return [value for value in x if not math.isnan(value)]


def convert_to_master_clock(line, line_clk, master_clock, fill_by_prev=False):
    """Takes a clock and generates an appropriate line with a value for each entry in clock. Values are taken from another line if the
    clock value in question is found in its line_clk. Otherwise NaN is used"""
    if master_clock is None:
        return line

    clk_offset = len(line_clk) - len(line)  # sometimes the clock has more data than the data line
    new_line = []
    next_start_idx = 0
    for sc in master_clock:
        found = False
        for i in range(next_start_idx, len(line_clk)):
            v = line_clk[i]
            if sc == v:
                # exact hit
                line_idx = i - clk_offset
                if line_idx < 0:
                    # data line is shorter so we don't have data
                    new_line.append(float('nan'))
                else:
                    new_line.append(line[line_idx])
                next_start_idx = i + 1
                found = True
                break
            elif v > sc:
                # no need to keep searching...
                break

        if not found:
            if len(new_line) > 0 and fill_by_prev:
                fill_v = new_line[-1]  # fill missing values with prev value
            else:
                fill_v = float('nan')  # fill with NaN, Bokeh wont plot
            new_line.append(fill_v)
    return new_line


def convert_to_pandas(master_clock, obj: bt.LineSeries, start: datetime = None, end: datetime = None, name_prefix: str = "", num_back=None) -> pd.DataFrame:
    lines_clk = obj.lines.datetime.plotrange(start, end)

    df = pd.DataFrame()
    # iterate all lines
    for lineidx in range(obj.size()):
        line = obj.lines[lineidx]
        linealias = obj.lines._getlinealias(lineidx)
        if linealias == 'datetime':
            continue

        # get data limited to time range
        data = line.plotrange(start, end)

        ndata = convert_to_master_clock(data, lines_clk, master_clock)

        df[name_prefix + linealias] = ndata

    df[name_prefix + 'datetime'] = [bt.num2date(x) for x in master_clock]

    return df


def get_clock_line(obj: Union[bt.ObserverBase, bt.IndicatorBase, bt.StrategyBase]):
    """Find the corresponding clock for an object. A clock is a datetime line that holds timestamps for the line in question."""
    if isinstance(obj, (bt.ObserverBase, bt.IndicatorBase)):
        return get_clock_line(obj._clock)
    elif isinstance(obj, (bt.StrategyBase, bt.AbstractDataBase)):
        clk = obj
    elif isinstance(obj, bt.LineSeriesStub):
        # indicators can be created to run on a single line (instead of e.g. a data object)
        # in that case we grab the owner of that line to find the corresponding clok
        return get_clock_line(obj._owner)
    elif isinstance(obj, bt.LineActions):
        # used for line actions like "macd > data[0]"
        return get_clock_line(obj._owner)
    else:
        raise Exception(f'Unsupported object type passed: {obj.__class__}')
    return clk.lines.datetime


def find_by_plotid(strategy: bt.Strategy, plotid):
    objs = itertools.chain(strategy.datas, strategy.getindicators(), strategy.getobservers())
    founds = []
    for obj in objs:
        if getattr(obj.plotinfo, 'plotid', None) == plotid:
            founds.append(obj)

    num_results = len(founds)
    if num_results == 0:
        return None
    elif num_results == 1:
        return founds[0]
    else:
        raise RuntimeError(f'Found multiple objects with plotid "{plotid}"')
