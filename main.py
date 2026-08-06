"""
Punto de entrada principal para interactuar con el agente.

Utiliza InMemoryRunner de ADK para ejecutar el agente en un entorno local de prueba,
gestionando el historial de la conversación y la invocación de herramientas.
"""

import asyncio
import os
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from src.agent import jobbud_agent

# Cargar variables de entorno desde el archivo .env
load_dotenv()


async def ejecutar_chat_interactivo():
    print("=" * 60)
    print("💼 JobBud - Asistente de Búsqueda Laboral (ADK)")
    print("Escribe 'salir' o 'exit' para terminar la conversación.")
    print("=" * 60)

    # El Runner administra la ejecución del agente y el flujo de sesión
    runner = InMemoryRunner(agent=jobbud_agent)

    while True:
        try:
            prompt_usuario = input("\n👤 Tú: ").strip()
            if not prompt_usuario:
                continue

            if prompt_usuario.lower() in ["salir", "exit", "quit"]:
                print("👋 ¡Hasta luego!")
                break

            print("💼 JobBud procesando...")
            respuesta = await runner.run_debug(prompt_usuario, verbose=False)
            print(f"\n💼 JobBud: {respuesta}")

        except KeyboardInterrupt:
            print("\n👋 Conversación interrumpida.")
            break
        except Exception as e:
            print(f"\n❌ Error al ejecutar el agente: {e}")


if __name__ == "__main__":
    asyncio.run(ejecutar_chat_interactivo())
