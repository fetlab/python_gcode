def listsplit(l, sep, keepsep=True):
	"""Return list l divided into chunks, separated whenever function sep(line)
	is True. Discard the separator if keepsep is False."""
	r = []
	a = []
	for i in l:
		if sep(i) and len(a) > 0:
			if keepsep:
				a.append(i)
			r.append(a)
			a = []
		else:
			a.append(i)
	return r
