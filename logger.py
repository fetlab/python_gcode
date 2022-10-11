import logging
from lablogging   import AccordionHandler
from rich_output_handler import RichOutputWidgetHandler
import rich.terminal_theme

rich_log = logging.getLogger('threader')
rich_log.setLevel(logging.DEBUG)

def rprint(*args, indent_char=' ', indent=0, **kwargs):
	msg = ''
	for i,arg in enumerate(args):
		if isinstance(arg, (list,tuple,set)):
			if len(arg) == 0:
				if i > 0: msg += ' '
				msg += str(arg)
			else:
				nl = '\n' + indent_char * indent
				if i > 0: msg += nl
				msg += nl.join(map(str,arg))
				if i < len(args)-1: msg += '\n'
		else:
			if i > 0: msg += ' '
			msg += str(arg)

	style = kwargs.get('style', {})
	if '\n' in msg:
		style.setdefault('line-height', 'normal')

	rich_log.debug(msg, extra={'style':style})


def reinit_logging(acclog=None):
	rich_log.removeHandler(acclog)
	acclog = AccordionHandler(
			default_title = 'Non-thread layers',
			handler_class = RichOutputWidgetHandler,
			handler_args  = {
				'theme': rich.terminal_theme.MONOKAI,
				'html_style': {'line-height': 2},
			})
	rich_log.addHandler(acclog)
	return acclog
