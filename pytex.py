import sys, yaml

def log(msg, verbose=False):
    global args
    if not verbose or args.verbose is True:
        print(msg)

config = {}
class args(object):
    __init__    = None
    config_file = 'pytex.yaml'
    verbose     = False

def parse_args():
    global args

    if len(sys.argv) <= 1:
        print(__doc__)
        sys.exit(1)

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


def main():
    global args, config
    parse_args()

    file = open(args.config_file, "r")
    cfg = file.read()
    file.close()

    config = yaml.load(cfg)

if __name__ == '__main__':
    main()