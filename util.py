from collections import namedtuple

Point3 = namedtuple('Point3', 'x y z')

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
