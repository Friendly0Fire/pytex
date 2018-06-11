# -*- coding: utf-8 -*-
import sys, yaml, platform, shutil, os, itertools, re, subprocess, gzip

#############
# UTILITIES #
#############

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
    'compile_command': None
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

##################
# LATEX HANDLING #
##################

def parse_latex_file(file, temporary_list):
    log("Parsing input file '" + file + "'...", True)
    output_lines = []

    if file == config['main_file']:
        output_lines.append(r"\newenvironment{pytex}{}{}")

    pyinput = ""
    inpyinput = False
    with open(file, "r") as f:
        for lno,l in enumerate(itertools.chain(f, [''])):
            lno += 1
            l = l.rstrip()

            if inpyinput:
                end_match = re.match(r"^\s*\\end\{pytex\}\s*(%.*)?$", l)
                if end_match is not None:
                    eval(pyinput) # FIXME: Handle scoping and errors
                    inpyinput = False
                else:
                    pyinput += l + "\n"
                    output_lines.append("%" + l)
                    continue

            # Parse for \begin{pytex} \end{pytex} here
            begin_match = re.match(r"^\s*\\begin\{pytex\}\s*(%.*)?$", l)
            if begin_match is not None:
                pyinput = ""
                inpyinput = True

            # Look for \input{file}
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
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fi,fo in temporary_list:
        os.remove(fo)

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