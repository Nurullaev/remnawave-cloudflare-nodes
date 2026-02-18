import asyncio
import signal
import sys

import uvicorn

from .config import Config
from .remnawave import RemnawaveClient, NodeMonitor
from .cloudflare_dns import CloudflareClient, DNSManager
from .monitoring_service import MonitoringService
from .telegram import TelegramNotifier, ServiceStarted
from .utils.logger import setup_logger


class GracefulExit(SystemExit):
    code = 0


def raise_graceful_exit(signum, frame):
    raise GracefulExit()


async def run_api_server(app, host: str, port: int) -> None:
    server_config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(server_config)
    server.install_signal_handlers = lambda: None  # our signal handlers manage shutdown
    await server.serve()


async def run_monitoring_loop(service: MonitoringService, interval: int, logger):
    logger.info(f"Starting monitoring loop with {interval}s interval")

    while True:
        try:
            await service.perform_health_check()

            logger.info(f"Waiting {interval} seconds until next check...")
            await asyncio.sleep(interval)

        except GracefulExit:
            logger.info("Received shutdown signal, stopping...")
            break
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, stopping...")
            break
        except Exception as e:
            logger.info(f"Retrying in {interval} seconds after error: {e}")
            await asyncio.sleep(interval)


async def main():
    config = Config()
    config.validate()

    logger = setup_logger(name="remnawave-cloudflare-monitor", level=config.log_level, log_file="logs/app.log")

    signal.signal(signal.SIGTERM, raise_graceful_exit)
    signal.signal(signal.SIGINT, raise_graceful_exit)

    logger.info("Starting Remnawave-Cloudflare DNS Monitor")
    logger.info(f"Check interval: {config.check_interval}s")

    remnawave_client = RemnawaveClient(api_url=config.remnawave_url, api_key=config.remnawave_api_key)

    node_monitor = NodeMonitor(remnawave_client)

    notifier = TelegramNotifier(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        topic_id=config.telegram_topic_id,
        locale=config.telegram_locale,
        enabled=config.telegram_enabled,
        notify_api_changes=config.telegram_notify_api_changes,
    )

    cloudflare_client = CloudflareClient(api_token=config.cloudflare_token)
    dns_manager = DNSManager(
        client=cloudflare_client,
        notifier=notifier,
        notify_dns_changes=config.telegram_notify_dns_changes,
        notify_errors=config.telegram_notify_errors,
    )

    monitoring_service = MonitoringService(
        config=config,
        node_monitor=node_monitor,
        cloudflare_client=cloudflare_client,
        dns_manager=dns_manager,
        notifier=notifier,
    )

    api_task = None

    try:
        await notifier.start()
        notifier.notify_service_started(
            ServiceStarted(
                domains=config.domains,
                api_enabled=config.api_enabled,
                api_host=config.api_host,
                api_port=config.api_port,
            )
        )

        await monitoring_service.initialize_and_print_zones()

        if config.api_enabled:
            from .api import create_app

            api_app = create_app(config, notifier, monitoring_service)
            api_task = asyncio.create_task(run_api_server(api_app, config.api_host, config.api_port))
            logger.info(f"API server listening on {config.api_host}:{config.api_port}")

        await run_monitoring_loop(service=monitoring_service, interval=config.check_interval, logger=logger)
    except (GracefulExit, KeyboardInterrupt):
        logger.info("Shutting down gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if api_task:
            api_task.cancel()
            try:
                await api_task
            except asyncio.CancelledError:
                pass
        notifier.notify_service_stopped()
        await notifier.stop()

    logger.info("Remnawave-Cloudflare DNS Monitor stopped")


if __name__ == "__main__":
    asyncio.run(main())
