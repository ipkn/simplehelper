try:
    from tkinter import *
    import tkinter.messagebox as tkmb
    import tkinter.filedialog as tkfd
    from tkinter.ttk import *
except:
    from Tkinter import *
    import tkMessageBox as tkmb
    import tkFileDialog as tkfd
import json
import threading
import time
import os
from importlib import import_module
import subprocess
import shutil
import sys

prepared_once = False
class Tool:
    def __init__(self, simpleperf_path, arch):
        self.simpleperf_path = simpleperf_path
        self.arch = arch
        self.subproc = None

    def running_time(self):
        return time.time() - self.startTime
    def is_running(self):
        if not self.subproc:
            return False
        print(repr(self.subproc.poll()))
        if self.subproc.poll() is not None:
            self.subproc = None
            self.post_collect_data()
            return False
        return True

    def post_collect_data(self):
        time.sleep(0.1)
        print('post_collect_data')
        self.adb('pull', '/data/local/tmp/perf.data', 'perf.data')

    def adb(self, *commands, **kwargs):
        print('\trunning', ' '.join(commands))
        return subprocess.check_output(['adb'] + list(commands))

    def prepare(self):
        global prepared_once
        print('prepared_once',prepared_once)
        if not prepared_once:
            print('prepared_once2',prepared_once)
            prepared_once = True
            self.upload_simpleperf()

    def upload_simpleperf(self):
        print('upload_simpleperf')
        self.adb('push',os.path.join(self.simpleperf_path, 'bin/android', self.arch, 'simpleperf'), '/data/local/tmp')
        self.adb('shell', 'chmod', 'a+x', '/data/local/tmp/simpleperf')
        time.sleep(1)

    def start(self, dur):
        print('profile start')
        self.subproc = subprocess.Popen(['adb', 'shell', '/data/local/tmp/simpleperf', 'record', '-o', '/data/local/tmp/perf.data', '--app', get_config('bundle'), '-g', '--duration', str(dur), '-f', '1000', '--exit-with-parent'])
        self.duration = dur
        self.startTime = time.time()

    def stop(self):
        print('profile stop')
        if self.subproc:
            self.subproc.kill()
            self.subproc.wait()
            time.sleep(1)
            print('stop wait')
            self.subproc = None

    def check_size(self, path='perf.data'):
        ret = self.adb('shell','run-as',get_config('bundle'), 'ls','-al',path, '2>/dev/null')
        if not ret:
            return 0
        return int(ret.split()[4])

def get_config(key, default = ''):
    if key in config:
        return config[key]
    return default

def set_config(k, v):
    config[k] = v

class UI:
    def loop(self):
        mainloop()

    def stop_profiler(self):
        self.tool.stop()
        self.run_btn.config(text='Start profiler', command=self.start_profiler)
        self.log.insert(END, 'Stopped.\n\n')
        self.log.yview(END)
        time.sleep(1)

    def start_profiler(self):
        self.runtime_error = False
        self.autoRestart = False
        self.log.insert(END, 'Profiling started. (number should be increasing.)'+'\n')
        self.log.yview(END)

        self.run_btn.config(text='Stop profiler', command=self.stop_profiler)
        path = self.pathVar.get()
        if not os.path.exists(os.path.join(path, "app_profiler.py")):
            tkmb.showerror("Cannot find simpleperf", "invalid simpleperf path")
            return
        self.tool = tool = Tool(path, self.arch.get())
        tool.prepare()
        try:
            dur = self.durationVar.get()
        except:
            dur = 10
            self.durationVar.set(dur)
        tool.start(dur)
        self.running = True
        self.infoVar.set('Running...')
        self.oldSize = 0

    def collect_symbols(self):
        try:
            open('perf.data')
        except:
            tkmb.showerror("Cannot find perf.data", "Run the profiler first.")
            return
        path = self.pathVar.get()
        if not os.path.exists(os.path.join(path, "app_profiler.py")):
            tkmb.showerror("Cannot find simpleperf", "invalid simpleperf path")
            return

        if path not in sys.path:
            sys.path.append(path)

        import binary_cache_builder as bcb
        config = {'perf_data_path':'perf.data', 'symfs_dirs':[],'disable_adb_root':True}
        builder = bcb.BinaryCacheBuilder(config)
        self.infoVar.set('Collecting symbols ...')
        def work():
            builder.build_binary_cache()
            self.infoVar.set('Done.')
        threading.Thread(target=work).start()

        # result stores to ./binary_cache

    def pick_symbol_path(self):
        d = tkfd.askopenfilename()
        if d:
            self.symbolPathVar.set(d)

    def pick_simpleperf_path(self):
        d = tkfd.askdirectory()
        if d:
            self.pathVar.set(d)

    def remove_collected_symbols(self):
        shutil.rmtree('binary_cache')

    def run_gui(self):
        self.infoVar.set('Running simpleperf report gui ... (see other window)')
        os.system('python '+os.path.join(self.pathVar.get(),'report.py')+' --gui -g --full-callgraph')
        self.infoVar.set('')

    def build_flamegraph(self):
        import urllib.request
        try:
            d = urllib.request.urlopen('http://ipkn.me:40041').read()
        except:
            tkmb.showerror("Server offline", "server is not working now. Can't build flamegraph")
            return
        import zipfile
        zf = zipfile.ZipFile('upload.zip', 'w', zipfile.ZIP_DEFLATED)
        zf.write('perf.data')
        for root, dirs, files in os.walk('binary_cache'):
            for f in files:
                zf.write(os.path.join(root, f))
        zf.close()
        d = urllib.request.urlopen('http://ipkn.me:40041/flamegraph', data=open('upload.zip', 'rb')).read()
        if d:
            file('flamegraph.svg','wb').write(d)
            import webbrowser
            webbrowser.open('flamegraph.svg')
        else:
            tkmb.showerror("Day limit exceeded.", "server is not working now. Can't build flamegraph")

    def __init__(self, rt):
        self.running = False
        self.autoRestart = False

        pad = 10

        self.rt = rt 

        f_right = Frame(rt)
        f_right.pack(side=RIGHT)

        self.log = Text(f_right, width=20, height=15)
        self.log.pack(fill=Y)

        f_upper = frame = Frame(rt)
        f_upper.pack()

        f1 = f_upper
        self.pathVar = pathVar = StringVar()
        pathVar.set(get_config('path', '.'))
        def update_path_var(*args):
            set_config('path', self.pathVar.get())
        pathVar.trace('w', update_path_var)
        w1 = Label(f1, text="simpleperf path:")
        w1.grid(row=0,column=0)
        text = Entry(f1, width = 30, textvariable = pathVar)
        text.grid(row=0, column=1)
        b1 = Button(f1, text="...", command=self.pick_simpleperf_path)
        b1.grid(row = 0, column=2)

        f2 = f_upper
        w2 = Label(f2, text="Bundle identifier:")
        w2.grid(row = 1, column = 0)
        self.bundleIdentifierVar = bundleIdentifierVar = StringVar()
        bundleIdentifierVar.set(get_config('bundle'))
        def update_bi_var(*args):
            set_config('bundle', bundleIdentifierVar.get())
        bundleIdentifierVar.trace('w', update_bi_var)
        text = Entry(f2, width = 30, textvariable = bundleIdentifierVar)
        text.grid(row = 1, column = 1)

        f4 = f_upper
        self.durationVar = durationVar = IntVar()
        durationVar.set(10)
        w4 = Label(f4, text="Profile duration (seconds):")
        w4.grid(row=2,column=0)
        text = Entry(f4, width=30, textvariable = durationVar)
        text.grid(row=2, column=1)

        f3 = f_upper
        self.symbolPathVar = pathVar = StringVar()
        #pathVar.set(get_config('symbol_path', '.'))
        #def update_symbol_path_var(*args):
            #set_config('symbol_path', self.symbolPathVar.get())
        #pathVar.trace('w', update_symbol_path_var)
        #w3 = Label(f3, text="symbol (.zip) path:")
        #w3.grid(row = 3, column = 0)
        #text = Entry(f3, width = 30, textvariable = pathVar)
        #text.grid(row = 3, column = 1)
        #b3 = Button(f3, text="...", command=self.pick_symbol_path)
        #b3.grid(row = 3, column=2)

        w4 = Label(f_upper, text="Arch.")
        w4.grid(row=4,column=0)
        self.arch = arch = Combobox(f_upper, values=["arm", "arm64", "x86", "x86_64"], state='readonly')
        arch.set("arm")
        arch.grid(row=4,column=1)

        f = Frame(rt)
        f.pack(fill=BOTH)

        f_start = Frame(f)
        f_start.pack(padx=pad, pady=pad,fill=BOTH)
        self.run_btn = run_btn = Button(f_start, text='Start profiler', command=self.start_profiler)
        #run_btn.pack(padx=pad, pady=pad, fill=X)
        run_btn.pack(fill=X)
        self.isAutoRestartVar = isAutoRestartVar = IntVar()
        check_btn = Checkbutton(f_start, text='Automatic restart profiler after a failure', variable=isAutoRestartVar, onvalue=1, offvalue=0)
        #check_btn.pack(padx=pad, pady=pad, fill=X)
        check_btn.pack(fill=X)
        collect_btn = Button(f, text='Collect symbol files', command=self.collect_symbols)
        collect_btn.pack(padx=pad, pady=pad, fill=X)
        clear_collection_btn = Button(f, text='Remove collected files', command=self.remove_collected_symbols)
        clear_collection_btn.pack(padx=pad, pady=pad, fill=X)
        gui_btn = Button(f, text='Run simpleperf report gui', command=self.run_gui)
        gui_btn.pack(padx=pad, pady=pad, fill=X)
        #graph_btn = Button(f, text='Build Flamegraph (*limited to build once per 23h, upload symbols to cloud server)', command=self.build_flamegraph)
        #graph_btn.pack(padx=pad, pady=pad, fill=X)
        self.infoVar = StringVar()
        self.state = state = Label(f, textvariable=self.infoVar)
        state.pack(padx = pad, pady=pad, fill=X)

        self.rt.after(100, self.timer)

    def timer(self):
        if self.running:
            if not self.tool.is_running():
                self.running = False
                if self.runtime_error and not self.autoRestart:
                    self.infoVar.set('Done. (failed to collect samples)')
                else:
                    self.infoVar.set('Done.')
                self.run_btn.config(text='Start profiler', command=self.start_profiler)
            else:
                newSize = self.tool.check_size()
                self.log.insert(END, str(newSize)+' ' + str(round(self.tool.running_time(), 3))+'\n')
                self.log.yview(END)
                if self.oldSize == newSize and (self.tool.running_time() > 3 and self.tool.running_time() < self.tool.duration):
                    self.infoVar.set('Running... (not updating)')
                    self.runtime_error = True
                    if self.isAutoRestartVar.get():
                        self.tool.stop()
                        self.autoRestart = True
                        self.infoVar.set('Restarting...')
                self.oldSize = newSize
        elif self.autoRestart:
            print('AUTO RESTART')
            time.sleep(1)
            self.autoRestart = False
            self.start_profiler()

        self.rt.after(300, self.timer)

def main():
    rt = Tk()
    rt.title("Simpleperf helper")

    ui = UI(rt)
    ui.loop()

if __name__ == '__main__':
    try:
        config = json.load(open('guiconfig.json'))
    except:
        config = {}
    try:
        main()
    finally:
        json.dump(config, open('guiconfig.json','w'))
