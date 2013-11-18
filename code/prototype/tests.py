import sys


class ppm_request():

	def __init__(self,type,headers,body):
		self.type = type
		self.headers = dict()
		self.body = body

		for key,val in headers.iteritems():
			print key,val
			self.headers[key] = val

	def package(self):
		message = 'PPM {}:\r\n\r\n'.format(self.type)
		for key,val in self.headers.iteritems():
			message+='{}={};\r\n'.format(key,val)
		message+=':\r\n\r\n'
		message+=self.body
		message+=':\r\n\r\n'
		return message

class ppm_response():

	def __init__(self,data):
		self.data = data
		self.headers = dict()
		self.payload = ''
		self.extract_headers()

	def extract_headers(self):
		parts = self.data.split(':\r\n\r\n')
		if 'PPM' not in parts[0]:
			print('invalid ppm message')

		for 
		print parts



if __name__ == '__main__':
	headers = dict()
	headers['range'] = 1024
	headers['url'] = 'happy.com'
	message = ppm_request(headers,'hello, world')
	ppm_response(message.package())
