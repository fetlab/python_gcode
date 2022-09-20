from collections  import namedtuple
from time         import time
from functools    import wraps
from operator     import itemgetter

Point3 = namedtuple('Point3', 'x y z')

def sign(n):
	return -1 if n < 0 else (1 if n > 0 else 0)

def construct_lines_rel2abs(gc_lines, start=0):
	"""Construct a list of GCLine objects, replacing the existing E values with
	absolute extrusion amounts based on each GCLine's relative_extrude value.
	Use start as the starting extrusion value. Return the constructed list and
	the ending extrusion value."""
	r = []
	ext_val = start
	for line in gc_lines:
		if 'E' in line.args and line.code in ['G0', 'G1']:
			try:
				ext_val += line.relative_extrude
			except AttributeError:
				r.append(line.construct())
			else:
				r.append(line.construct(E=f'{ext_val:.5f}'))
		else:
			r.append(line.construct())
	return r, ext_val


def find_lineno(lineno, steps=None, gcsegs=None, gc_lines=None):
	if gc_lines:
		return any([l for l in gc_lines if l.lineno == lineno])
	if gcsegs:
		return {f'Seg {i}': seg for i,seg in enumerate(gcsegs) if
				find_lineno(lineno, gc_lines=seg.gc_lines)}
	if steps:
		return dict(filter(itemgetter(1),
			[(f'Step {i}', find_lineno(lineno, gcsegs=step.gcsegs))
				for i,step in enumerate(steps)]))


def listsplit(l, sepfunc, maxsplit=-1, keepsep='>', minsize=0):
	"""Return list l divided into chunks, separated whenever function sepfunc(line)
	is True. Discard the separator if keepsep is False. If keepsep is '<' save the
	separator at the end of the chunk; if it's '>' save it in the start of the
	next chunk. If a chunk is less than minsize in length, combine it with
	the next chunk."""
	r = []
	a = []
	ll = iter(l)
	for e in ll:
		if sepfunc(e) and a:
			if keepsep == '<':
				a.append(e)
			if len(a) >= minsize:
				r.append(a)
				a = []
			if keepsep == '>':
				a.append(e)
			if maxsplit > -1 and len(r) >= maxsplit:
				r.append(a + list(ll))
				a = []
				break
		else:
			a.append(e)
	if a:
		r.append(a)
	return r


def find(lst, func=None, rev=False):
	"""Return the first item in the list that is true. Pass an optional
	evaluation function. Set rev to True to search backwards."""
	lst = reversed(lst) if rev else lst
	return next(filter(func, lst), None)


def listsplit2(l, sepfunc, maxsplit=-1, keepsep='>'):
	r = []
	start = 0
	end   = None
	for i,e in enumerate(l):
		if sepfunc(e):
			end = i
			if keepsep == '<':
				end += 1
			r.append(l[start:end])
			if maxsplit > -1 and len(r) >= maxsplit:
				r.append(l[end:])
				end = None
				break
			start = end + 1
			end = None
		else:
			end = i
	if end:
		r.append(l[start:end+1])
	return r


def timing(f):
	@wraps(f)
	def wrap(*args, **kwargs):
		start = time()
		result = f(*args, **kwargs)
		end = time()
		print(f'{f.__name__} took {end-start:2.4f}s')
		return result
	return wrap


#Source https://github.com/pydantic/pydantic/blob/317bef33b06e05f65f57b1ba009dfd949b462689/pydantic/utils.py#L215
def deep_update(mapping, *updating_mappings):
	updated_mapping = mapping.copy()
	for updating_mapping in updating_mappings:
		for k, v in updating_mapping.items():
			if k in updated_mapping and isinstance(updated_mapping[k], dict) and isinstance(v, dict):
				updated_mapping[k] = deep_update(updated_mapping[k], v)
			else:
				updated_mapping[k] = v
	return updated_mapping


class Restore:
	def __init__(self, obj, vars):
		self.saved = {v: getattr(obj, v) for v in vars}
		self.obj = obj
		self.changed = {}

	def __enter__(self):
		return self

	def __exit__(self, exc_type, value, tb):
		if exc_type is not None:
			return False
		for var,oldval in self.saved.items():
			newval = getattr(self.obj, var)
			if newval != oldval:
				self.changed[var] = newval
			setattr(self.obj, var, oldval)



class Saver:
	"""Save values for variables in save_vars that have changed."""
	def __init__(self, obj, save_vars):
		self.saved = {v: getattr(obj, v) for v in save_vars}
		self.obj = obj
		self.changed = {}

	def __enter__(self):
		return self

	def __exit__(self, exc_type, value, tb):
		from threader import rprint
		rprint(f'--- Saver exit: {self}\n---')
		if exc_type is not None:
			return False
		for var,oldval in self.saved.items():
			newval = getattr(self.obj, var)
			if newval != oldval:
				self.changed[var] = newval

	def __repr__(self):
		return('\n'.join([
				f'{var}: {val} -> {self.changed.get(var, "")}'
				for var,val in self.saved.items()]))
