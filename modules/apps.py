from django.apps import AppConfig


class ModulesConfig(AppConfig):
    
    name = 'modules'

    def ready(self):
        import modules.signals  # noqa
