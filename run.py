import sys
from canvasindexer import create_app

app = create_app()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        app.run(debug=True, port=5005)
    else:
        app.run()
