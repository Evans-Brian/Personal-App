"""Evening prompt upgrades and exact moves selected by private review."""
from migrate_evening_prompts import COMBINED_PROMPT, MERGED_PROMPTS, evening_blocks

NEGATIVE_PROMPT = 'Negative feelings today'
PROUD_PROMPT = 'What am I proud of today?'
DIFFERENT_PROMPT = 'What would I do differently if I replayed today?'
SOURCES = {COMBINED_PROMPT, PROUD_PROMPT, DIFFERENT_PROMPT}


def negative_answer(text):
    return '\n\n'.join(text[body:end].strip() for start, body, end, title in evening_blocks(text)
                       if title == NEGATIVE_PROMPT and text[body:end].strip())


def with_negative_feelings(text, fallback=''):
    blocks = evening_blocks(text)
    titles = {title for _, _, _, title in blocks}
    if NEGATIVE_PROMPT in titles or not SOURCES.issubset(titles):
        return text
    start = next(start for start, body, end, title in blocks if title == PROUD_PROMPT)
    nl = '\r\n' if '\r\n' in text else '\n'
    section = '### ' + NEGATIVE_PROMPT + nl * 2 + (fallback.strip() + nl * 2 if fallback.strip() else nl)
    return text[:start] + section + text[start:]


def move_reviewed_passages(text, moves):
    """Move exact reviewed excerpts; do not infer sentiment or rewrite the prose."""
    text = with_negative_feelings(text)
    nl = '\r\n' if '\r\n' in text else '\n'
    moved = []
    empty_labels = {label + ':' for label in MERGED_PROMPTS.values()}
    for move in moves:
        question, excerpt = move['question'], move['excerpt']
        if question not in SOURCES or not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError('A move must name a narrative question and a nonempty exact excerpt.')
        sources = [block for block in evening_blocks(text) if block[3] == question]
        if len(sources) != 1:
            raise ValueError('The source question is missing or duplicated; no safe move is possible.')
        start, body, end, title = sources[0]
        answer = text[body:end]
        count = answer.count(excerpt)
        if count == 0 and excerpt.strip() in negative_answer(text):
            continue
        if count != 1:
            raise ValueError('The reviewed excerpt is missing or ambiguous; review the note again.')
        remaining = answer.replace(excerpt, '', 1)
        if not remaining.strip() or remaining.strip() in empty_labels:
            remaining = nl * 2
        text = text[:body] + remaining + text[end:]
        moved.append(excerpt.strip())
    if moved:
        destinations = [block for block in evening_blocks(text) if block[3] == NEGATIVE_PROMPT]
        if len(destinations) != 1:
            raise ValueError('The negative-feelings question is missing or duplicated.')
        start, body, end, title = destinations[0]
        previous = text[body:end].strip()
        answer = (nl * 2).join(([previous] if previous else []) + moved)
        text = text[:body] + nl + answer + nl * 2 + text[end:]
    return text
