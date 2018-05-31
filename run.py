import sys
from canvasindexer import create_app

debug = False
if len(sys.argv) > 1 and sys.argv[1] == 'debug':
    debug = True

app = create_app(debug=debug)

if __name__ == '__main__':
    app.run(debug=debug, port=5005, use_reloader=False)
