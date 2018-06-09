import sys, yaml, platform, shutil, os

def log(msg, verbose=False):
    global args
    if not verbose or args.verbose is True:
        print(msg)

def load_yaml(file):
    fstream = open(file, "r")
    fcontents = fstream.read()
    fstream.close()

    return yaml.load(fcontents)

# "Sensible" defaults for compiling the processed output file
default_compile_commands = {
    "latexmk": "latexmk -pdf $file",
    "texify": "texify --pdf $file",
    "rubber": "rubber --pdf $file",
    "pdflatex": "pdftex $file"
}

# Configuration settings read from the config files
config = {
    'output_ext': '.c.tex',
    'user_config_file': 'pytex.user.yaml',
    'main_file': "main.tex",
    'compile_command': None
}
class args(object):
    __init__    = None
    config_file = 'pytex.yaml'
    verbose     = False

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
    if config.user_config_file is not None and os.path.isfile(config.user_config_file):
        loaded_config = load_yaml(config.user_config_file)
        config = {**config, **loaded_config}

    # Simple sanity checks once config is loaded

    if not os.path.isfile(config.main_file):
        print("Could not find main file '" + config.main_file + "'; aborting.")
        sys.exit(1)

    if config.output_ext is None or len(config.output_ext) <= 1:
        print("Output extension '" + config.output_ext + "' is invalid; aborting.")
        sys.exit(1)

    # If the compile command has not been set in any config file,
    # try to automatically determine a sensible one by fishing
    # for a recognized LaTeX compiler
    if config.compile_command is None:

        for compile_exec, compile_command in default_compile_commands:
            if shutil.which(compile_exec) is not None:
                config.compile_command = compile_command
                break

        if config.compile_command is None:
            print("Unrecognized LaTeX platform and no compile command provided; aborting.")
            sys.exit(1)



def main():
    parse_args()
    load_config()


if __name__ == '__main__':
    main()