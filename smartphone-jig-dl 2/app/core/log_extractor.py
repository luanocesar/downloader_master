def extract_value(line, from_word, pos_from, pos_to, end_word=""):
    if from_word:
        idx = line.find(from_word)
        if idx == -1:
            return ""
        start = idx + len(from_word) + max(pos_from, 0)
    else:
        start = max(pos_from, 0)

    if start > len(line):
        return ""

    end = len(line)
    if end_word:
        end_idx = line.find(end_word, start)
        if end_idx != -1:
            end = end_idx
    if pos_to and pos_to > 0:
        end = min(end, start + pos_to)
    if end <= start:
        return ""

    return line[start:end]


def extract_field_from_range(lines, field):
    row_marker = field.get("row_marker", "")
    source = next((line for line in lines if row_marker in line), "") if row_marker else "\n".join(lines)
    if row_marker and not source:
        return ""
    return extract_value(
        source, field.get("from_word", ""), field.get("pos_from", 0),
        field.get("pos_to", 0), field.get("end_word", ""),
    )


def run_extraction(lines, start_marker, end_marker, fields):
    """Agrupa `lines` em blocos delimitados por start_marker/end_marker e
    extrai `fields` de cada bloco. `lines` são linhas já sem terminador de
    quebra (rstrip("\\n\\r"))."""
    results = []
    pending_range = None

    for line in lines:
        if start_marker in line:
            pending_range = [line]
            if end_marker in line:
                results.append({field["name"]: extract_field_from_range(pending_range, field) for field in fields})
                pending_range = None
            continue

        if pending_range is not None:
            pending_range.append(line)
            if end_marker in line:
                results.append({field["name"]: extract_field_from_range(pending_range, field) for field in fields})
                pending_range = None

    return results
