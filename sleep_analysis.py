"""Local Oura sleep analysis. Stage-derived timings are estimates, never diagnoses."""
from datetime import date, datetime, timedelta
import json
import math
import re
from statistics import mean, median, pstdev
from urllib.parse import unquote


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def minutes(value):
    value = number(value)
    return round(value / 60, 2) if value is not None and value >= 0 else None


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def aggregate(values):
    values = [value for value in values if number(value) is not None]
    return {'n': len(values), 'mean': round(mean(values), 2) if values else None,
            'median': round(median(values), 2) if values else None,
            'sd': round(pstdev(values), 2) if values else None}


def clock_minutes(value, bedtime=False):
    parsed = stamp(value)
    if parsed is None:
        return None
    result = parsed.hour * 60 + parsed.minute + parsed.second / 60
    return result + 1440 if bedtime and result < 720 else result


def session(record):
    start, end = stamp(record.get('bedtime_start')), stamp(record.get('bedtime_end'))
    if start is None or end is None or end <= start:
        return None
    duration = (end - start).total_seconds()
    result = {'id': record['id'], 'day': record['day'], 'type': record.get('type'),
              'bedtime': start.isoformat(), 'out_of_bed': end.isoformat(),
              'asleep_minutes': minutes(record.get('total_sleep_duration')),
              'in_bed_minutes': minutes(record.get('time_in_bed')),
              'awake_minutes': minutes(record.get('awake_time')),
              'latency_minutes': minutes(record.get('latency')),
              'deep_minutes': minutes(record.get('deep_sleep_duration')),
              'rem_minutes': minutes(record.get('rem_sleep_duration')),
              'light_minutes': minutes(record.get('light_sleep_duration')),
              'efficiency': number(record.get('efficiency')),
              'hrv': number(record.get('average_hrv')), 'heart_rate': number(record.get('average_heart_rate')),
              'lowest_heart_rate': number(record.get('lowest_heart_rate')),
              'breathing_rate': number(record.get('average_breath')),
              'restless_periods': number(record.get('restless_periods')),
              'low_battery': record.get('low_battery_alert') is True,
              'algorithm': record.get('sleep_algorithm_version'),
              'offset_changed': start.utcoffset() != end.utcoffset(),
              'onset': None, 'final_wake': None, 'waso_minutes': None,
              'longest_wake_minutes': None, 'awakenings_5m': None,
              'stage_resolution_seconds': None, 'stage_coverage': None, 'stages': [], 'awakenings': [], 'disrupted_windows': [],
              'samples': {key: record.get(key) for key in ('heart_rate', 'hrv')},
              'movement_30_sec': record.get('movement_30_sec'), 'onset_source': None}
    # Prefer the highest resolution supplied by the API, never infer stages from HR.
    phases, interval = '', 0
    for key, seconds in [('sleep_phase_30_sec', 30), ('sleep_phase_5_min', 300)]:
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate and set(candidate) <= set('1234'):
            phases, interval = candidate, seconds
            break
    if phases:
        coverage = min(len(phases) * interval / duration, 1)
        result['stage_resolution_seconds'] = interval
        result['stage_coverage'] = round(coverage, 3)
        # Avoid precise-looking wake statistics when a stage series is truncated or mismatched.
        if abs(len(phases) * interval - duration) <= max(interval * 2, duration * .02):
            runs = []
            for index, phase in enumerate(phases):
                left, right = index * interval, min((index + 1) * interval, duration)
                if left >= right:
                    break
                if runs and runs[-1]['stage'] == phase:
                    runs[-1]['end_seconds'] = right
                else:
                    runs.append({'stage': phase, 'start_seconds': left, 'end_seconds': right})
            result['stages'] = runs
            asleep = [run for run in runs if run['stage'] != '4']
            if asleep:
                onset, final = asleep[0]['start_seconds'], asleep[-1]['end_seconds']
                result['onset'] = (start + timedelta(seconds=onset)).isoformat()
                result['final_wake'] = (start + timedelta(seconds=final)).isoformat()
                result['onset_source'] = 'sleep stages'
                wakes = [run for run in runs if run['stage'] == '4' and run['start_seconds'] >= onset and run['end_seconds'] <= final]
                result['waso_minutes'] = round(sum(run['end_seconds'] - run['start_seconds'] for run in wakes) / 60, 2)
                result['longest_wake_minutes'] = round(max((run['end_seconds'] - run['start_seconds'] for run in wakes), default=0) / 60, 2)
                result['awakenings_5m'] = sum(run['end_seconds'] - run['start_seconds'] >= 300 for run in wakes)
                for run in wakes:
                    result['awakenings'].append({
                        'start': (start + timedelta(seconds=run['start_seconds'])).isoformat(),
                        'end': (start + timedelta(seconds=run['end_seconds'])).isoformat(),
                        'minutes': round((run['end_seconds'] - run['start_seconds']) / 60, 2)})
                clusters = []
                for wake in result['awakenings']:
                    if clusters and (stamp(wake['start']) - stamp(clusters[-1]['end'])).total_seconds() <= 300:
                        clusters[-1]['end'] = wake['end']
                        clusters[-1]['awake_minutes'] += wake['minutes']
                    else:
                        clusters.append({'start':wake['start'], 'end':wake['end'], 'awake_minutes':wake['minutes']})
                result['disrupted_windows'] = [
                    {**cluster, 'span_minutes':round((stamp(cluster['end'])-stamp(cluster['start'])).total_seconds()/60, 2)}
                    for cluster in clusters if cluster['awake_minutes'] >= 20]
    if result['onset'] is None and result['latency_minutes'] is not None and result['latency_minutes'] * 60 < duration:
        result['onset'] = (start + timedelta(minutes=result['latency_minutes'])).isoformat()
        result['onset_source'] = 'bedtime + reported latency'
    return result


def metadata(journal, day, period, marker):
    if not journal or not journal.path(day).exists():
        return {}
    text = journal.read(day)['sections'][period]
    match = re.search(r'<!-- ' + re.escape(marker) + r': (.*?) -->', text)
    try:
        value = json.loads(unquote(match[1])) if match else {}
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def caffeine_log(habits):
    """Keep unknown logs and old checkbox answers distinct from precise intake times."""
    intake = habits.get('caffeine_last_intake')
    if intake == 'none':
        return intake, False
    if isinstance(intake, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', intake):
        return intake, intake > '16:00'
    if 'caffeine_last_intake' in habits:
        return None, None
    legacy = habits.get('caffeine_after_4pm')
    return None, legacy if isinstance(legacy, bool) else None


METRICS = ('asleep_minutes', 'in_bed_minutes', 'awake_minutes', 'waso_minutes', 'latency_minutes',
           'longest_wake_minutes', 'awakenings_5m', 'efficiency', 'hrv', 'heart_rate',
           'lowest_heart_rate', 'breathing_rate', 'deep_minutes', 'rem_minutes', 'light_minutes',
           'spo2', 'breathing_disturbance_index', 'sleep_score', 'temperature_deviation',
           'bedtime_clock', 'onset_clock', 'wake_clock')


def insights(nights, summary, comparison):
    result = []
    if not nights:
        return ['No main-sleep sessions in this range. Import history or choose another range.']
    total = summary['asleep_minutes']['median']
    if total is not None:
        result.append(f'Median main sleep is {round(total)} minutes; median time in bed is {round(summary["in_bed_minutes"]["median"] or 0)} minutes across {len(nights)} recorded nights.')
    staged = [night for night in nights if night['waso_minutes'] is not None]
    if staged:
        long20 = sum(night['longest_wake_minutes'] >= 20 for night in staged)
        long60 = sum(night['longest_wake_minutes'] >= 60 for night in staged)
        result.append(f'{long20} of {len(staged)} nights with usable stages have a continuous overnight awakening of at least 20 minutes; {long60} have one of at least an hour. These exclude time before first sleep and after final sleep.')
        result.append(f'Median awake time between first and last sleep is {round(summary["waso_minutes"]["median"])} minutes. Oura’s total awake-in-bed metric also includes the edges of the night, so it can be higher.')
    if summary['bedtime_clock']['sd'] is not None and summary['wake_clock']['sd'] is not None:
        result.append(f'Clock-time variability is about {round(summary["bedtime_clock"]["sd"])} minutes for bedtime and {round(summary["wake_clock"]["sd"])} minutes for waking (standard deviations). This describes consistency, not a target sleep schedule.')
    months = {}
    for night in staged:
        months.setdefault(night['day'][:7], []).append(night['waso_minutes'])
    comparable = [(month, values) for month, values in sorted(months.items()) if len(values) >= 7]
    if len(comparable) > 1:
        earlier, later = comparable[0], comparable[-1]
        result.append(f'Awake time during sleep averaged {round(mean(earlier[1]))} minutes in {earlier[0]} ({len(earlier[1])} nights) and {round(mean(later[1]))} minutes in {later[0]} ({len(later[1])} nights). These months may be incomplete and have unequal coverage.')
    if comparison:
        for metric, title in [('asleep_minutes', 'Time asleep'), ('waso_minutes', 'Awake time during sleep')]:
            current, previous = comparison['recent'][metric], comparison['previous'][metric]
            if current['n'] >= 5 and previous['n'] >= 5:
                delta = round(current['mean'] - previous['mean'])
                result.append(f'{title} averaged {round(current["mean"])} minutes in the latest 14 calendar days versus {round(previous["mean"])} in the preceding 14 ({delta:+d} minutes; {current["n"]} vs {previous["n"]} recorded nights).')
    caffeine = [night for night in nights if night['caffeine_after_4pm'] is not None and night['waso_minutes'] is not None]
    yes, no = [night['waso_minutes'] for night in caffeine if night['caffeine_after_4pm']], [night['waso_minutes'] for night in caffeine if not night['caffeine_after_4pm']]
    if len(yes) >= 5 and len(no) >= 5:
        result.append(f'After reported caffeine past 4 p.m., awake time during sleep averaged {round(mean(yes))} minutes ({len(yes)} nights), versus {round(mean(no))} without it ({len(no)} nights). This is an association and does not establish a cause.')
    else:
        result.append(f'Caffeine comparison needs more logged nights: {len(yes)} with late caffeine and {len(no)} without it have usable stages. Missing logs are unknown; older checkbox answers do not supply an exact intake time.')
    # Compare the self-report against the same morning's overnight estimate.
    disagreements = [night for night in staged if night['reported_sleep'].get('awake_1_hour') is True and night['longest_wake_minutes'] < 60]
    if disagreements:
        result.append(f'On {len(disagreements)} logged nights you reported being awake at least an hour, but the ring detected no single hour-long awakening. Quiet wakefulness can be missed; keep your own report alongside the ring estimate.')
    return result


def analyze(store, journal=None, start=None, end=None, analysis_start=None):
    end = end or date.today().isoformat()
    start = start or (date.fromisoformat(end) - timedelta(days=89)).isoformat()
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last - first).days > 6000:
        raise ValueError('Choose a sleep range of at most 6,000 days, with start before end.')
    if analysis_start:
        cutoff = date.fromisoformat(analysis_start)
        if last < cutoff:
            raise ValueError(f'Sleep analysis starts on {cutoff.isoformat()}. Earlier data is ignored.')
        # Ignore data before the locally chosen baseline in every dashboard calculation.
        first = max(first, cutoff)
        start = first.isoformat()
    records = store.read_range(start, end)
    by_kind = {}
    sessions = []
    for row in records:
        record = row['data']
        if row['kind'] == 'sleep' and record.get('type') not in ('deleted', 'rest'):
            value = session(record)
            if value:
                sessions.append(value)
        elif row['kind'] != 'sleep':
            by_kind.setdefault(row['kind'], {})[record['day']] = record
    days = {}
    for item in sessions:
        days.setdefault(item['day'], []).append(item)
    nights = []
    for day, periods in sorted(days.items()):
        main = [item for item in periods if item['type'] == 'long_sleep']
        # Old records without a type are usable if they describe a genuine overnight interval.
        main += [item for item in periods if item['type'] is None and (item['in_bed_minutes'] or 0) >= 180]
        if not main:
            continue
        night = dict(max(main, key=lambda item: item['asleep_minutes'] or 0))
        night['period_count'] = len(periods)
        night['main_period_count'] = len(main)
        night['all_sleep_minutes'] = round(sum(item['asleep_minutes'] or 0 for item in periods), 2)
        night['bedtime_clock'] = clock_minutes(night['bedtime'], bedtime=True)
        night['onset_clock'] = clock_minutes(night['onset'], bedtime=True)
        night['wake_clock'] = clock_minutes(night['final_wake'] or night['out_of_bed'])
        summary = by_kind.get('daily_sleep', {}).get(day, {})
        readiness = by_kind.get('daily_readiness', {}).get(day, {})
        spo2 = by_kind.get('daily_spo2', {}).get(day, {})
        night.update(sleep_score=summary.get('score'), contributors=summary.get('contributors', {}),
                     readiness_score=readiness.get('score'), temperature_deviation=readiness.get('temperature_deviation'),
                     spo2=(spo2.get('spo2_percentage') or {}).get('average'),
                     breathing_disturbance_index=spo2.get('breathing_disturbance_index'),
                     bedtime_recommendation=by_kind.get('sleep_time', {}).get(day),
                     daytime_stress=by_kind.get('daily_stress', {}).get(day))
        # After-midnight bedtimes follow the preceding waking day's caffeine report.
        bedtime = stamp(night['bedtime'])
        caffeine_day = bedtime.date() - timedelta(days=1 if bedtime.hour < 12 else 0)
        habits = metadata(journal, caffeine_day.isoformat(), 'evening', 'evening-habits')
        night['caffeine_last_intake'], night['caffeine_after_4pm'] = caffeine_log(habits)
        night['caffeine_day'] = caffeine_day.isoformat()
        night['reported_sleep'] = metadata(journal, day, 'morning', 'morning-sleep')
        nights.append(night)
    summary = {key: aggregate([night[key] for night in nights]) for key in METRICS}
    monthly = []
    for month in sorted({night['day'][:7] for night in nights}):
        group = [night for night in nights if night['day'].startswith(month)]
        monthly.append({'month':month, 'n':len(group),
                        'asleep':aggregate([night['asleep_minutes'] for night in group]),
                        'awake':aggregate([night['waso_minutes'] for night in group]),
                        'latency':aggregate([night['latency_minutes'] for night in group])})
    comparison = None
    if nights:
        anchor = date.fromisoformat(nights[-1]['day'])
        recent = [night for night in nights if date.fromisoformat(night['day']) > anchor - timedelta(days=14)]
        previous = [night for night in nights if anchor - timedelta(days=28) < date.fromisoformat(night['day']) <= anchor - timedelta(days=14)]
        comparison = {'recent': {key: aggregate([night[key] for night in recent]) for key in METRICS},
                      'previous': {key: aggregate([night[key] for night in previous]) for key in METRICS}}
    bins = []
    for hour in range(24):
        overlaps = []
        for night in nights:
            if night['waso_minutes'] is None:
                continue
            for wake in night['awakenings']:
                if wake['minutes'] < 5:
                    continue
                left, right = stamp(wake['start']), stamp(wake['end'])
                cursor = left.replace(minute=0, second=0, microsecond=0)
                while cursor < right:
                    until = cursor + timedelta(hours=1)
                    if cursor.hour == hour:
                        overlaps.append((min(right, until) - max(left, cursor)).total_seconds() / 60)
                    cursor = until
        bins.append({'hour': hour, 'awake_minutes': round(sum(overlaps), 2)})
    return {'start': start, 'end': end, 'analysis_start': analysis_start,
            'inventory': store.inventory(start=analysis_start), 'nights': nights, 'monthly':monthly,
            'sessions': sorted(sessions, key=lambda item: item['bedtime']), 'summary': summary,
            'comparison': comparison, 'wake_hours': bins, 'insights': insights(nights, summary, comparison),
            'coverage': {'nights': len(nights), 'stage_nights': sum(night['waso_minutes'] is not None for night in nights),
                         'calendar_days': (last-first).days+1,
                         'missing_days': (last-first).days+1-len(nights)},
            'method': 'One longest main-sleep session per Oura-assigned day drives nightly trends. All other sessions remain in the night view. Awake during sleep sums stage-awake intervals between first and last sleep; awakening counts use continuous runs of at least five minutes. Times use each recorded UTC offset; stage timestamps keep the start offset on nights crossing an offset change. Ring estimates can miss quiet wakefulness. No data is inferred across gaps or missing nights.'}
