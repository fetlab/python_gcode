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


def listsplit2(l, sep, maxsplit=-1, keepsep='>'):
	r = []
	start = 0
	end   = None
	for i,e in enumerate(l):
		if sep(e):
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
