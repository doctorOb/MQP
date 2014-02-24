from Crypto.PublicKey import RSA
from Crypto import Random



if __name__ == '__main__':
	
	keys = {}

	ips = ['127.0.0.1:1337','127.0.0.1:8080']
	for i in ips:
		random_generator = Random.new().read
		key = RSA.generate(1024, random_generator)
		keys[i] = key.exportKey()

	with open('keys.txt','w') as f:
		f.write(str(keys))





