styles: dict[str, dict] = {
	#Generic styles
	'segments':     {'mode': 'lines', 'line': dict(color='blue', width=1)},
	'points':       {'mode': 'markers', 'marker': dict(color='violet',  symbol='circle', size=4)},
	'circles':      {'line':  dict(color='magenta', width=1)},

	#Thread styles
	'original_thread': {'line': dict(color='coral',     width=.5, dash='dot')},
	'thread_ring':     {'line': dict(color='white',     width=1,  dash='dot')},
	'future_thread':   {'line': dict(color='yellow',    width=1,  dash='dot')},
	'moved_thread':    {'line': dict(color='cyan',      width=.5, dash='dot')},
	'printed_thread':  {'line': dict(color='olivedrab', width=1,  dash='dot')},

	#Anchors
	'anchor':          {'marker': dict(color='red',    symbol='x', size=4)},
	'original_anchor': {'marker': dict(color='coroal', symbol='x', size=4)},

	#GCode segment styles
	'gc_segs':    {'line': dict(color='green',     width=2)},
	'old_layer':  {'line': dict(color='gray',      width=.5), 'opacity': .25},
	'old_segs':   {'line': dict(color= 'gray',     width=1)},
	'to_print':   {'line': dict(color='green',     width=.5), 'opacity': .25},
	'avoid_segs': {'line': dict(color='firebrick', width=1)}



	#'bed':        {'line': dict(color='rgba(0,0,0,0)'), 'fillcolor': 'LightSkyBlue', 'opacity':.25},
	# 'ring':       {'line': dict(color='white', width=10), 'opacity':.25},
	# 'indicator':  {'line': dict(color='blue',  width= 4)},
}
