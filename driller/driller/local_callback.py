import os
import sys
import signal
import logging
import logging.config
import driller
import argparse
import subprocess
import multiprocessing
import time 
l = logging.getLogger("local_callback")
#long
l.setLevel(logging.DEBUG)

def _run_drill(drill, fuzz, _path_to_input_to_drill, length_extension=None):
    _binary_path = fuzz.binary_path
    _fuzzer_out_dir = fuzz.out_dir
    _bitmap_path = os.path.join(_fuzzer_out_dir, 'fuzzer-master', "fuzz_bitmap")
    _timeout = drill._worker_timeout
    #long
    #t1=time.time()
    l.warning("starting drilling of %s, %s", os.path.basename(_binary_path), os.path.basename(_path_to_input_to_drill))
    args = (
        "timeout", "-k", str(_timeout+10), str(_timeout),
        sys.executable, os.path.abspath(__file__),
        _binary_path, _fuzzer_out_dir, _bitmap_path, _path_to_input_to_drill
    )
    if length_extension:
        args += ('--length-extension', str(length_extension))

    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    print p.communicate()
    #t2=time.time()
    #l.warning('onetime!!!!!!!')
    #l.warning(str( (int(round((t2-t1) * 1000)))))


class LocalCallback(object):
    def __init__(self, num_workers=1, worker_timeout=10*60, length_extension=None):
        self._already_drilled_inputs = set()

        self._num_workers = num_workers
        self._running_workers = []
        self._worker_timeout = worker_timeout
        self._length_extension = length_extension

    @staticmethod
    def _queue_files(fuzz, fuzzer='fuzzer-master'):
        '''
        retrieve the current queue of inputs from a fuzzer
        :return: a list of strings which represent a fuzzer's queue
        '''

        queue_path = os.path.join(fuzz.out_dir, fuzzer, 'queue')
        queue_files = filter(lambda x: x != ".state", os.listdir(queue_path))
        queue_files = [os.path.join(queue_path, q) for q in queue_files]

        return queue_files
    #long
    @staticmethod
    def _queue_files_driller(fuzz, fuzzer='driller'):
        '''
        retrieve the current queue of inputs from a fuzzer
        :return: a list of strings which represent a fuzzer's queue
        '''
        try:
            queue_path = os.path.join(fuzz.out_dir, fuzzer, 'queue')
            queue_files = filter(lambda x: x != ".state", os.listdir(queue_path))
            queue_files = [os.path.join(queue_path, q) for q in queue_files]
        except:
            queue_files=[]

        return queue_files    
    def driller_callback(self, fuzz):
        #l.warning("Driller stuck callback triggered!")
        # remove any workers that aren't running
        self._running_workers = [x for x in self._running_workers if x.is_alive()]

        # get the files in queue
        #long
        queue = self._queue_files(fuzz)
        queue1= self._queue_files_driller(fuzz)
        queue.extend(queue1)
        #for i in range(1, fuzz.fuzz_id):
        #    fname = "fuzzer-%d" % i
        #    queue.extend(self.queue_files(fname))

        # start drilling
        not_drilled = set(queue) - self._already_drilled_inputs
        #l.warning(repr(not_drilled))
        if len(not_drilled) == 0:
            l.warning("no inputs left to drill")

        while len(self._running_workers) < self._num_workers and len(not_drilled) > 0:
            to_drill_path = list(not_drilled)[0]
            not_drilled.remove(to_drill_path)
            self._already_drilled_inputs.add(to_drill_path)

            proc = multiprocessing.Process(target=_run_drill, args=(self, fuzz, to_drill_path),
                    kwargs={'length_extension': self._length_extension})
            proc.start()
            self._running_workers.append(proc)
    __call__ = driller_callback
    
    def kill(self):
        for p in self._running_workers:
            try:
                p.terminate()
                os.kill(p.pid, signal.SIGKILL)
            except OSError:
                pass

# this is for running with bash timeout
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Driller local callback")
    parser.add_argument('binary_path')
    parser.add_argument('fuzzer_out_dir')
    parser.add_argument('bitmap_path')
    parser.add_argument('path_to_input_to_drill')
    parser.add_argument('--length-extension', help="Try extending inputs to driller by this many bytes", type=int)
    args = parser.parse_args()

    logcfg_file = os.path.join(os.getcwd(), '.driller.ini')
    if os.path.isfile(logcfg_file):
        logging.config.fileConfig(logcfg_file)

    binary_path, fuzzer_out_dir, bitmap_path, path_to_input_to_drill = sys.argv[1:5]
    #long bitmap origin is string, now change to list
    #l.warning(args.bitmap_path)
    fuzzer_bitmap = list(open(args.bitmap_path, "r").read())

    # create a folder
    driller_dir = os.path.join(args.fuzzer_out_dir, "driller")
    driller_queue_dir = os.path.join(driller_dir, "queue")
    #long
    #driller_queue_dir=args.fuzzer_out_dir

    try: os.mkdir(driller_dir)
    except OSError: pass
    try: os.mkdir(driller_queue_dir)
    except OSError: pass

    l.warning('drilling %s', path_to_input_to_drill)
    # get the input
    inputs_to_drill = [open(args.path_to_input_to_drill, "r").read()]
    if args.length_extension:
        inputs_to_drill.append(inputs_to_drill[0] + '\0' * args.length_extension)

    for input_to_drill in inputs_to_drill:
        d = driller.Driller(args.binary_path, input_to_drill, fuzzer_bitmap) #add bitmap
        count = 0
        for new_input in d.drill_generator():
            id_num = len(os.listdir(driller_queue_dir))
            fuzzer_from = args.path_to_input_to_drill.split("sync/")[1].split("/")[0] + args.path_to_input_to_drill.split("id:")[1].split(",")[0]
            filepath = "id:" + ("%d" % id_num).rjust(6, "0") + ",from:" + fuzzer_from
            filepath = os.path.join(driller_queue_dir, filepath)
            #long write file
            #fuzzer_from = os.path.basename(args.path_to_input_to_drill).split('id:')[1].split(',')[0]
            #filepath = "id:" + ("%d" % id_num).rjust(6, "0") + ",from:" + fuzzer_from
            #filepath = os.path.join(driller_queue_dir, filepath)
            #long 
            debug_flag=1
            if debug_flag:
                l.warning("found %d new inputs:%s", count,repr(new_input[1]))

            #with open(filepath, "wb") as f:
            #    f.write(new_input[1])

            #long check diff
            find_same_flag=0
            for driller_sample in os.listdir(driller_queue_dir):
                driller_sample_path=os.path.join(driller_queue_dir, driller_sample)
                r=open(driller_sample_path,'r')
                content=r.read().rstrip(b'\0')
                r.close()
                #l.waring()
                if content==new_input[1].rstrip(b'\0'):
                    find_same_flag=1
                    break

            if find_same_flag==0:
                l.warning('generating '+filepath+' from '+path_to_input_to_drill)
                myfile=open(filepath,'wb')
                myfile.write(new_input[1])
                myfile.close()
            else:
                l.warning('the same sample')
                #os.system('rm '+filepath)
            count += 1
    #long print the string solved
    l.warning("found %d new inputs", count)
    
