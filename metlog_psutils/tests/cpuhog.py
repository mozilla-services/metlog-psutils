"""
This is used by metlog-psutils's test to check for out of process CPU
usage
"""
import time
time.sleep(1)
for i in range(20000):
    for j in range(7, 20):
        x = j ** 25
time.sleep(1)
print x
