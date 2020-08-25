from labjack import ljm
import numpy as np
from datetime import datetime
import time
import sys
import signal


def connect_to_LJ():
    handle = ljm.openS("T7", "ANY", "ANY")
    info = ljm.getHandleInfo(handle)
    print("Opened a LabJack with Device type: %i, Connection type: %i,\n"
          "Serial number: %i, IP address: %s, Port: %i,"
          "\nMax bytes per MB: %i" %
          (info[0], info[1], info[2],
           ljm.numberToIP(info[3]), info[4], info[5]))
    return handle


def fname_from_time(preamble):
    dt = datetime.now()
    return f"{preamble}_{dt.strftime('%Y_%m_%d_%H00')}.csv"


def append_to_file(fname, data):
    with open(fname, 'ab+') as f:
        np.savetxt(f, data, delimiter=', ')


def volt_to_temp(V, temp_scale, voltage_offset):
    return temp_scale * V + voltage_offset


def stream_to_file(handle,
                   samples_per_point,
                   points_per_write,
                   sampling_rate,
                   address_names,
                   fname_preamble,
                   temp_scale=50,
                   voltage_offset=0.):

    def signal_handler(signal, frame):
        global stop_scan
        stop_scan = True
        print("Stopping scan (KeyboardInterrupt)")

    signal.signal(signal.SIGINT, signal_handler)
    mean_vector = np.zeros(samples_per_point)
    write_buffer = np.zeros((points_per_write, 2))
    num_addresses = len(address_names)
    aScanList = ljm.namesToAddresses(num_addresses, address_names)[0]
    start = 0
    tot_scans = 0
    tot_skip = 0
    total_points = 0
    try:
        ljm.eWriteName(handle, "STREAM_TRIGGER_INDEX", 0)
        ljm.eWriteName(handle, "STREAM_CLOCK_SOURCE", 0)

        scanRate = ljm.eStreamStart(handle, sampling_rate, num_addresses,
                                    aScanList, sampling_rate)
        print(f"Stream started with {sampling_rate:.1f} Hz sampling rate")

        start = datetime.now()
        means = 0
        points = 0
        stop_scan = False
        while not stop_scan:
            ret = ljm.eStreamRead(handle)
            aData = ret[0]
            tot_scans += len(aData)
            mean_vector[means] = np.mean(aData)
            # Count the skipped samples which are indicated by -9999 values.
            # Missed samples occur after a device's stream buffer overflows and
            # are reported after auto-recover mode ends.
            cur_skip = aData.count(-9999.0)
            tot_skip += cur_skip
            means += 1
            if means == samples_per_point:
                write_buffer[points, :] = [time.time(),
                                           volt_to_temp(np.mean(mean_vector),
                                                        50.,
                                                        0.)]
                points += 1
                means = 0
                mean_vector = np.zeros(samples_per_point)
            if points == points_per_write:
                fname = fname_from_time(fname_preamble)
                print(f"writing to file {fname}")
                append_to_file(fname, write_buffer)
                points = 0
                write_buffer = np.zeros((points_per_write, 2))
                total_points += points_per_write

    except ljm.LJMError:
        print(sys.exc_info()[1])
    except Exception:
        print(sys.exc_info()[1])
    finally:
        fname = fname_from_time(fname_preamble)
        print(f"writing to file {fname}")
        append_to_file(fname, write_buffer[np.nonzero(write_buffer[:, 1])])
        total_points += len(np.nonzero(write_buffer))
        end = datetime.now()
        print("\nTotal scans = %i" % (tot_scans))
        print("\nTotal points saved = %i" % (total_points))
        tt = (end - start).seconds + float((end - start).microseconds) / 1e6
        print("Time taken = %f seconds" % (tt))
        print("LJM Scan Rate = %f scans/second" % (scanRate))
        print("Timed Scan Rate = %f scans/second" % (tot_scans / tt))
        print("Timed Sample Rate = %f samples/second"
              % (tot_scans * num_addresses / tt))
        print("Skipped scans = %0.0f" % (tot_skip / num_addresses))
        try:
            print("Stopping stream.")
            ljm.eStreamStop(handle)
        except ljm.LJMError:
            print(sys.exc_info()[1])
        except Exception:
            print(sys.exc_info()[1])
        return {'Total scans': tot_scans,
                'Saved points': total_points,
                'Scan time': tt,
                'LJM scan rate': scanRate,
                'Timed scan rate': tot_scans/tt,
                'Timed sample rate': tot_scans * num_addresses / tt,
                'Skipped scans': tot_skip / num_addresses}


if __name__ == "__main__":
    handle = connect_to_LJ()
    stream_to_file(handle=handle,
                   samples_per_point=2,
                   points_per_write=1,
                   sampling_rate=1,
                   address_names=['AIN1'],
                   fname_preamble='testing_temp')
    ljm.close(handle)
