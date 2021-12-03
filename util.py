from collections import namedtuple

Point3 = namedtuple('Point3', 'x y z')

def listsplit(l, sep, maxsplit=-1, keepsep='>'):
	"""Return list l divided into chunks, separated whenever function sep(line)
	is True. Discard the separator if keepsep is False. If keepsep is '<' save the
	separator at the end of the chunk; if it's '>' save it in the start of the
	next chunk."""
	r = []
	a = []
	ll = iter(l)
	for i in ll:
		if sep(i) and a:
			if keepsep == '<':
				a.append(i)
			r.append(a)
			a = []
			if keepsep == '>':
				a.append(i)
			if maxsplit > -1 and len(r) >= maxsplit:
				r.append(a + list(ll))
				a = []
				break
		else:
			a.append(i)
	if a:
		r.append(a)
	return r
