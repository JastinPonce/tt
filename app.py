import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- COMANDOS DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respuesta al comando /start"""
    await update.message.reply_text(
        "¡Hola! Tu nuevo bot está 100% vivo, limpio y corriendo en Render. "
        "Ahora puedes actualizarlo como tú quieras."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respuesta al comando /ayuda"""
    await update.message.reply_text("Los comandos disponibles son:\n/start - Iniciar bot\n/ayuda - Mostrar este menú")


# --- SERVIDOR WEB FALSIFICADO PARA RENDER ---
# Render necesita detectar un puerto web abierto o apagará el bot.
class HealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is running smoothly!")

def run_health_server(port):
    server = HTTPServer(("0.0.0.0", port), HealthCheckServer)
    server.serve_forever()


# --- ARRANQUE PRINCIPAL ---
if __name__ == "__main__":
    # 1. Obtener variables del entorno de Render
    PORT = int(os.environ.get("PORT", 8080))
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("ERROR: No se encontró la variable TELEGRAM_TOKEN")
        exit(1)

    # 2. Iniciar el servidor web en un hilo secundario para que Render esté contento
    server_thread = threading.Thread(target=run_health_server, args=(PORT,), daemon=True)
    server_thread.start()
    print(False, f"Servidor web de respuesta iniciado en el puerto {PORT}")

    # 3. Configurar e iniciar el Bot de Telegram de forma directa
    print("Iniciando el bot de Telegram...")
    application = Application.builder().token(token=TOKEN).build()
    
    # Registrar los comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", ayuda))
    
    # Arrancar el bucle continuo del bot
    application.run_polling()

# Variables globales del Blueprint del negocio
FEE_PERCENTAGE = 0.01  # 1% Comisión Total (0.5% para cada uno)
DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"  # Tu billetera cripto

# La billetera del socio se puede setear dinámicamente por entorno por cada canal que dupliques
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0xBilleteraDelSocioAqui") 

# Conexión nativa con la red Base a través de Web3.py
w3 = Web3(Web3.HTTPProvider('https://mainnet.base.org'))
