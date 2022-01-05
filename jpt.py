import jupytext

def find_cell(lines, linenr):
	text = '\n'.join(lines)
	fmt = jupytext.formats.long_form_one_format(
			jupytext.formats.divine_format(text))
	impl = jupytext.formats.get_format_implementation(fmt['extension'],
		fmt.get('format_name'))
	metadata, jupyter_md, header_cell, pos = jupytext.header.header_to_metadata_and_cell(
			lines, impl.header_prefix, impl.extension, None)
	default_language = jupytext.languages.default_language_from_metadata_and_ext(
			metadata, impl.extension)

	lines = lines[pos:]

	cellnr = 0
	curpos = pos
	while lines:
		reader = impl.cell_reader_class(fmt, default_language)
		cell, pos = reader.read(lines)
		curpos += pos
		lines = lines[pos:]
		if curpos >= linenr:
			return cellnr
		cellnr += 1
	return -1
