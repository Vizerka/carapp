from car_manager import create_app

app = create_app()

if __name__ == "__main__":
    # LAN: host 0.0.0.0
    app.run(host="0.0.0.0", port=5000, debug=True)