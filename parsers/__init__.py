import pkgutil, importlib

def get_parsers():
	return pkgutil.iter_modules([__name__])


def find_parser(lines):
	for module in get_parsers():
		m = importlib.import_module(f'.{module.name}', __name__)
		if m.detect(lines):
			return m
	raise ValueError("No parsers match")


__all__ = [find_parser]
