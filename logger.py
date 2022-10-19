import logging
from lablogging   import AccordionHandler
from rich_handler import RichHandler
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
	div   = kwargs.get('div', False)
	if '\n' in msg:
		style.setdefault('line-height', 'normal')

	rich_log.debug(msg, extra={'style':style, 'div':div})


def restart_logging():
	for handler in rich_log.handlers:
			rich_log.removeHandler(handler)


def reinit_logging(acclog=None):
	if acclog is None and rich_log.hasHandlers():
		for handler in rich_log.handlers:
			if isinstance(handler, AccordionHandler):
				rich_log.removeHandler(handler)
	else:
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


def end_accordion_logging():
	for handler in rich_log.handlers:
		if isinstance(handler, (AccordionHandler,RichHandler,RichOutputWidgetHandler)):
			rich_log.removeHandler(handler)
	rich_log.addHandler(RichHandler(
			theme=rich.terminal_theme.MONOKAI,
			html_style={'line-height': 2},
		))


def get_accordion():
	acc = next(filter(lambda h: isinstance(h, AccordionHandler), rich_log.handlers), None)
	if acc is None:
		reinit_logging()
		return get_accordion()
	return acc


def get_output():
	acc = get_accordion()
	if acc.out_handler is None:
		acc.add_fold()
	return acc.out_handler
