"""
This is used by metlog-psutils's test to check for out of process CPU
usage
"""


def main():
    for i in range(200000):
        for j in range(7, 20):
            x = j ** 25
    x = x

if __name__ == '__main__':
    main()
