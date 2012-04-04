from metlog_psutils.psutil_plugin import process_details
import time

def wait_for_network_shutdown():
    while True:
        details = process_details(net=True)
        if len(details['net']) > 0:
            time.sleep(1)
            print "Not all networks connections are closed...  waiting"
        else:
            print "Connections all closed - running testcase!"
            break
