# -*- coding: utf-8 -*-
import sys, yaml, platform, shutil, os, itertools, re, subprocess

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
    'output_file': None,
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

    if config['output_file'] is None:
        (root, ext) = os.path.splitext(config['main_file'])
        config['output_file'] = root + ".c" + ext

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

def parse_latex_file(file):
    log("Parsing input file '" + file + "'...", True)
    output_lines = []

    if file == config['main_file']:
        output_lines.append(r"\newenvironment{pytex}{}{}")

    rundir = os.path.dirname(file)
    prevrundir = None
    if rundir:
        prevrundir = os.getcwd()
        os.chdir(rundir)

    file = os.path.basename(file)
    with open(file, "r") as f:
        for lno,l in enumerate(itertools.chain(f, [''])):
            lno += 1
            l = l.rstrip()

            # Parse for \begin{pytex} \end{pytex} here

            # Look for \input{file}
            input_match = re.match(r"^\s*\\input\{(?P<inputfile>.+)\}\s*(%.*)?$", l)
            if input_match is not None:
                input_file = input_match.group("inputfile")
                if not os.path.isfile(input_file):
                    input_file += ".tex"
                if os.path.isfile(input_file):
                    output_lines += parse_latex_file(input_file) #FIXME: This shouldn't dump all the files in one, it should generate separate .c.tex files then clean them up afterwards
                l = None

            if l is not None:
                output_lines.append(l)

    if prevrundir:
        os.chdir(prevrundir)
    return output_lines

def parse_latex():
    global config

    outdir = os.path.dirname(config['output_file'])
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    with open(config['output_file'], "w") as f:
        lines = parse_latex_file(config['main_file'])
        compiled = "\n".join(lines)
        f.write(compiled)

def compile_latex():
    rundir = os.path.dirname(config['output_file'])
    fname = os.path.basename(config['output_file'])
    os.chdir(rundir)
    cmd = config['compile_command'].replace("$file", fname)
    subprocess.run(cmd)
    os.remove(fname)
    #FIXME: Fix ouput files, .log and .synctex files to use the right file names

def main():
    os.system(r'texify --verbose --synctex --pdf --clean --tex-option="-interaction=nonstopmode" --tex-option="-file-line-error" D:/FriendlyFire/Desktop/pytex/test/gxd.tex')
    return
    log("Parsing command arguments...", True)
    parse_args()
    log("Loading configuration files...", True)
    load_config()
    log("Parsing LaTeX input files...", True)
    parse_latex()
    log("Producing final LaTeX file and passing to compiler...", True)
    compile_latex()

if __name__ == '__main__':
    main()