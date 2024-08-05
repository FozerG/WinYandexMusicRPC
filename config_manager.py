import configparser
import os
import tempfile

class ConfigManager:
    def __init__(self, config_file='settings.ini', temp_dir_name="WinYandexMusicRPC"):
        self.temp_dir = os.path.join(tempfile.gettempdir(), temp_dir_name)
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        self.config_file = os.path.join(self.temp_dir, config_file)
        self.config = configparser.ConfigParser()
        self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            with open(self.config_file, 'w') as file:
                self.config.write(file)

    def get_setting(self, section, option, fallback=None):
        if self.config.has_option(section, option):
            return self.config.get(section, option)
        else:
            if fallback is not None:
                self.set_setting(section, option, fallback)
            return fallback

    def set_setting(self, section, option, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, value)
        self._save_config()

    def _save_config(self):
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)

    def set_enum_setting(self, section, option, enum_value):
        self.set_setting(section, option, enum_value.name)

    def get_enum_setting(self, section, option, enum_type, fallback=None):
        value = self.get_setting(section, option, fallback=fallback.name if fallback else None)
        if value in enum_type.__members__:
            return enum_type[value]
        else:
            self.set_enum_setting(section, option, fallback)
            return fallback