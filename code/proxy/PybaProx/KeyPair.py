from Crypto.PublicKey import RSA
from Crypto.Hash import MD5
from Crypto import Random

import os

from Logger import Logger
from proxyHelpers import md5hash


class PKeyPair():
	"""
	class for managing a public/private key pair for a router. Upon first instantiation, 
	a new key is generated and saved as a .key file under the routers IP address or provided name (alias).
	Subsequent invocations with similar parameters will import the key from the file.
	Provides necessary encrypt / decrypt functionality.
	"""
	def __init__(self,ip,fname=None,alias=None):
		self.ip = ip
		self.fname = fname if fname else '{}.key'.format(ip)
		self.log = Logger()
		if os.path.exists(self.fname):
			self._import()
		else:
			self.key = self._generate()
			self._export()

	def _export(self):
		with open(self.fname,'w') as f:
			f.write(self.key.exportKey())

	def _import(self):
		self.log.info("Importing Public/Private key pair from {}".format(self.fname))
		with open(self.fname,'r') as f:
			self.key = RSA.importKey(f.read())

	def _generate(self,size=1024):
		self.log.info("Generating new Public/Private key pair")
		random_generator = Random.new().read
		return RSA.generate(size,random_generator)

	def sign(self,msg):
		hash = md5hash(msg)
		return self.key.sign(hash,'')

	def verify(self,hash,signature):
		"""verify the computed hash against a signature, supposedly generated 
		by this instance's key"""
		return self.key.publickey().verify(hash,signature)

if __name__ == '__main__':
	#create a key when invoked as a script, optionally pass in an ip explicitly
	from proxyHelpers import get_ip
	import sys

	if len(sys.argv) > 1:
		ip = str(sys.argv[1])
	else:
		ip = get_ip()

	key = PKeyPair(ip)






