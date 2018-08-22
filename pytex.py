# -*- coding: utf-8 -*-
import sys, yaml, platform, shutil, os, itertools, re, subprocess, gzip, shlex, threading, queue, time

#############
# UTILITIES #
#############

def enqueue_output(out, queue, prepend=""):
    try:
        for line in iter(out.readline, b''):
            l = line.rstrip()
            if l != '':
                queue.put(prepend + l)
    except ValueError:
        return

def log(msg, verbose=False):
    global args
    if not verbose or args.verbose is True:
        print(msg)

def load_yaml(file):
    with open(file, "r") as fstream:
        return yaml.load(fstream)

def add_suffix(fullname):
    global config
    (name, ext) = os.path.splitext(fullname)
    return name + config['output_suffix'] + ext

#################
# CONFIGURATION #
#################

# "Sensible" defaults for compiling the processed output file
default_compile_commands = {
    "latexmk": "latexmk -pdf $file",
    "texify": "texify --pdf $file",
    "rubber": "rubber --pdf $file",
    "pdflatex": "pdftex $file"
}

# Configuration settings read from the config files
config = {
    'output_suffix': '.c',
    'user_config_file': 'pytex.user.yaml',
    'main_file': "main.tex",
    'compile_command': None,
    'begin_marker': '@py{',
    'end_marker': '}py@',
    'output_marker': '<-'
}
class args(object):
    __init__    = None
    config_file = 'pytex.yaml'
    verbose     = True

def parse_args():
    global args

    if len(sys.argv) <= 1:
        return

    idx = 1
    while idx < len(sys.argv):
        arg = sys.argv[idx]
        if arg in ['-c', '--config']:
            idx += 1
            args.config_file = sys.argv[idx]
        elif arg in ['-v', '--verbose']:
            args.verbose = True
        elif arg in ['-h', '--help']:
            print(__doc__)
            sys.exit(0)

        idx += 1

def load_config():
    global args, config, default_compile_commands

    # First load the base config file and override
    # any default option with those found in the file
    loaded_config = load_yaml(args.config_file)
    config = {**config, **loaded_config}

    # If the user config is set, load afterwards,
    # overriding both defaults and base config options
    if config['user_config_file'] is not None and os.path.isfile(config['user_config_file']):
        loaded_config = load_yaml(config['user_config_file'])
        config = {**config, **loaded_config}

    # Simple sanity checks once config is loaded

    if not os.path.isfile(config['main_file']):
        log("Could not find main file '" + config['main_file'] + "'; aborting.")
        sys.exit(1)

    if config['output_suffix'] is None:
        config['output_suffix'] = ".c"

    # If the compile command has not been set in any config file,
    # try to automatically determine a sensible one by fishing
    # for a recognized LaTeX compiler
    if config['compile_command'] is None:

        for compile_exec, compile_command in default_compile_commands:
            if shutil.which(compile_exec) is not None:
                config['compile_command'] = compile_command
                break

        if config['compile_command'] is None:
            log("Unrecognized LaTeX platform and no compile command provided; aborting.")
            sys.exit(1)

#############################
# LATEX CUSTOM PYTHON SCOPE #
#############################

class Scope(object):
    def __init__(self):
        self.out = None

    @staticmethod
    def get():
        global _mainScope
        return _mainScope

    def execute(self, code, output):
        self.out = output
        exec(code, vars(self))
        self.out = None
_mainScope = Scope()

##################
# LATEX HANDLING #
##################

def runPython(code, output_lines):
    global config

    codelines = [i.rstrip() for i in code.splitlines(False)]
    finalcode = ""
    for codeline in codelines:
        codematch = re.match(r"^(?P<indent>\s*)" + re.escape(config['output_marker']) + r"(\((?P<marker>.*)\))?\s+(?P<text>.*)$", codeline)
        if codematch is not None:
            textline = "\"" + codematch.group("text") + "\""

            varmarker = "@@"
            if codematch.group("marker") is not None:
                varmarker = codematch.group("marker")

            inlinevars = re.findall(re.escape(varmarker) + r"[a-zA-Z0-9_\-]+", textline)
            for inlinevar in inlinevars:
                textline = textline.replace(inlinevar, "\" + " + inlinevar[len(varmarker):] + " + \"")

            finalcode += codematch.group("indent") + "out.append(" + textline + ")\n"
        else:
            finalcode += codeline + "\n"

    Scope.get().execute(finalcode, output_lines)

def parse_latex_file(file, temporary_list):
    global config
    log("Parsing input file '" + file + "'...", True)
    output_lines = []

    if file == os.path.basename(config['main_file']):
        output_lines.append(r"\newenvironment{pytex}{}{}")
        sanitized_begin = config['begin_marker']
        sanitized_end = config['end_marker']
        for (a, b) in [("{", "\\{"), ("}", "\\}"), ("\\", "\\\\")]:
            sanitized_begin = sanitized_begin.replace(a, b)
            sanitized_end = sanitized_end.replace(a, b)

        output_lines.append(r"\newcommand{pytexinlinebegin}{%s}" % (sanitized_begin))
        output_lines.append(r"\newcommand{pytexinlineend}{%s}" % (sanitized_end))

    pyinput = ""
    inpyinput = False

    pyinline = ""
    inpyinline = False
    pyinlineloc = (-1, -1)
    end_marker_len = len(config['end_marker'])
    begin_marker_len = len(config['begin_marker'])
    with open(file, "r") as f:
        for lno,l in enumerate(itertools.chain(f, [''])):
            l = l.rstrip()

            # If already in \begin{pytex}, look for \end{pytex} or collect the code for evaluation
            if inpyinput:
                end_match = re.match(r"^\s*\\end\{pytex\}\s*(%.*)?$", l)
                if end_match is not None:
                    runPython(pyinput, output_lines)
                    inpyinput = False
                else:
                    pyinput += l + "\n"
                continue

            # Look for @py{<code>}py@, potentially across multiple lines
            py_match = 0
            while True:
                if inpyinline:
                    pyend_match = l.find(config['end_marker'], py_match)
                    if pyend_match != -1:
                        pyinline += l[py_match:pyend_match] + "\n"
                        l = l[:py_match-begin_marker_len] + l[pyend_match+end_marker_len:]
                        inpyinline = False
                    else:
                        pyinline += l[py_match:] + "\n"
                        l = l[:py_match-begin_marker_len]

                if not inpyinline and pyinline != "":
                    temp_out = []
                    runPython(pyinline[:-1], temp_out)

                    if pyinlineloc[0] == lno:
                        l = l[:pyinlineloc[1]] + "\n".join(temp_out) + l[pyinlineloc[1]:]
                    else:
                        l2 = output_lines[lno]
                        output_lines[lno] = l2[:pyinlineloc[1]] + "\n".join(temp_out) + l2[pyinlineloc[1]:]

                    pyinline = ""
                    pyinlineloc = (-1, -1)

                newpy_match = l.find(config['begin_marker'], py_match)
                if newpy_match != -1:
                    py_match = newpy_match + begin_marker_len
                    inpyinline = True
                    pyinlineloc = (lno, newpy_match)
                else:
                    break

            # Look for \begin{pytex}
            begin_match = re.match(r"^\s*\\begin\{pytex\}\s*(%.*)?$", l)
            if begin_match is not None:
                pyinput = ""
                inpyinput = True
                continue

            # Look for \input{file} and \include{file}
            input_match = re.match(r"^\s*\\((?P<isinput>input)|(?P<isinclude>include))\{(?P<inputfile>.+)\}\s*(%.*)?$", l)
            if input_match is not None:
                input_file = input_match.group("inputfile")
                if not os.path.isfile(input_file):
                    input_file += ".tex"
                if os.path.isfile(input_file):
                    parse_latex_file(input_file, temporary_list)
                    l = r"\%s{%s}" % ("include" if input_match.group("isinclude") != None else "input", os.path.splitext(add_suffix(input_file))[0])
                else:
                    l = None

            if l is not None:
                output_lines.append(l)

    generated_file = add_suffix(file)
    temporary_list.append((file, generated_file))
    with open(generated_file, "w") as f:
        compiled = "\n".join(output_lines)
        f.write(compiled)

def parse_latex(temporary_list):
    global config

    path = os.path.dirname(config['main_file'])
    file = os.path.basename(config['main_file'])

    if path:
        os.chdir(path)

    parse_latex_file(file, temporary_list)

def fix_synctex(basename, temporary_list):
    fstream = None
    isgz = False
    if os.path.isfile(basename + ".synctex.gz"):
        fstream = gzip.open(basename + ".synctex.gz", "rt")
        isgz = True
    elif os.path.isfile(basename + ".synctex"):
        fstream = open(basename + ".synctex", "r")

    if fstream is None:
        return

    outstr = ""
    with fstream:
        for lno,l in enumerate(itertools.chain(fstream, [''])):
            lno += 1

            if l.startswith("Input:"):
                for ri,ro in temporary_list:
                    l = l.replace(ro, ri)
                    # Windows-specific fix
                    l = l.replace(ro.replace("/", "\\"), ri.replace("/", "\\"))

            outstr += l.rstrip() + "\n"

    if isgz:
        fstream = gzip.open(basename + ".synctex.gz", "wt")
    else:
        fstream = open(basename + ".synctex", "w")

    with fstream:
        fstream.write(outstr)

def compile_latex(temporary_list):
    fname = add_suffix(os.path.basename(config['main_file']))
    cmd = config['compile_command'].replace("$file", fname)
    cmd = shlex.split(cmd)
    q = queue.Queue()
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True, encoding="utf8", errors="ignore") as proc:
        t = threading.Thread(target=enqueue_output, args=(proc.stdout, q, "O> "))
        t.daemon = True
        t.start()
        t2 = threading.Thread(target=enqueue_output, args=(proc.stderr, q, "E> "))
        t2.daemon = True
        t2.start()
        while proc.poll() is None or not q.empty():
            try:
                line = q.get_nowait()
                log(line)
                q.task_done()
            except queue.Empty:
                time.sleep(0.25)
                pass
        log("Compiler return code: " + str(proc.returncode))
        proc.stdout.close()
        proc.stderr.close()

    for _,fo in temporary_list:
        for i in range(1, 3+1):
            try:
                os.remove(fo)
                break
            except PermissionError:
                log("Could not delete file %s, %s" % (fo, "retrying..." if i < 3 else "giving up."))
                time.sleep(1)

    log("Fixing output file names...", True)
    outnamenoext = os.path.splitext(fname)[0]
    innamenoext = os.path.splitext(os.path.basename(config['main_file']))[0]
    for ext in [".log", ".pdf", ".synctex.gz", ".synctex"]:
        if os.path.isfile(outnamenoext + ext):
            with open(outnamenoext + ext, "rb") as istream:
                with open(innamenoext + ext, "wb") as ostream:
                    ostream.write(istream.read())
            os.remove(outnamenoext + ext)

    log("Fixing synctex, if set...", True)
    fix_synctex(innamenoext, temporary_list)

def main():
    log("Parsing command arguments...", True)
    parse_args()
    log("Loading configuration files...", True)
    load_config()

    log("Parsing LaTeX input files...", True)
    temporary_list = []
    parse_latex(temporary_list)

    log("Producing final LaTeX file and passing to compiler...", True)
    compile_latex(temporary_list)

if __name__ == '__main__':
    main()