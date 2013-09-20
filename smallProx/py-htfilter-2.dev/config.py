def configuration():
	return {
#		'chain':	('194.176.176.82',8080),
		'hooks':	('hook-youtube.py',),
		'buffer':	0,	# 0: none, 1: pass, 2: hold
		'chunk':	1048576,	# size of transfer chunk
		'cache':	{
			'youtube':	'cache'
		}
	}
