import pkgutil, importlib

def get_parsers():
	"""Return the list of available parser names. Make sure the basic parser is
	always last in the list."""
	mods = [m.name for m in filter(
		lambda m:m.name != 'basic', pkgutil.iter_modules([__name__]))]
	mods.append('basic')
	return mods


def find_parser(lines):
	for modname in get_parsers():
		m = importlib.import_module(f'.{modname}', __name__)
		if m.detect(lines):
			return m
	raise ValueError("No parsers match")


__all__ = [find_parser]
