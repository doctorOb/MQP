import sys
import proxyHelpers


v = proxyHelpers.BitVector()

v.push(1)
v.push(1)
v.push(0)
v.push(1)

print v.vector
print v.value()
print v.complement()