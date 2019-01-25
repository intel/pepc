Use the 'argparse-manpage' tool to generate man pages. It can be
installed with 'pip' or from the OS package. For example, Fedora
comes with the 'python3-argparse-manpage' package.

Change directory to 'pepc' git repository clone directory. To build
'pepc' tool man page, run:

  argparse-manpage --pyfile ./pepclibs/pepc.py --function build_arguments_parser \
                   --project-name 'pepc' --author 'Artem Bityutskiy' \
                   --author-email 'dedekind1@gmail.com' --output docs/man1/pepc.1
