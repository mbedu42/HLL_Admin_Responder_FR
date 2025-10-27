from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class RconCommands:
    """Helper class for common RCON commands"""
    
    @staticmethod
    def get_players_command() -> str:
        """Get command to list all players"""
        return "get players"
    
    @staticmethod
    def get_player_info_command(player_name: str) -> str:
        """Get command to get specific player info"""
        return f'playerinfo "{player_name}"'
    
    @staticmethod
    def kick_player_command(player_name: str, reason: str = "") -> str:
        """Get command to kick a player"""
        if reason:
            return f'kick "{player_name}" "{reason}"'
        return f'kick "{player_name}"'
    
    @staticmethod
    def ban_player_command(player_name: str, reason: str = "", duration: str = "") -> str:
        """Get command to ban a player"""
        if duration and reason:
            return f'ban "{player_name}" "{reason}" {duration}'
        elif reason:
            return f'ban "{player_name}" "{reason}"'
        return f'ban "{player_name}"'
    
    @staticmethod
    def message_player_command(player_name: str, message: str) -> str:
        """Get command to message a player"""
        return f'message "{player_name}" "{message}"'
    
    @staticmethod
    def broadcast_command(message: str) -> str:
        """Get command to broadcast to all players"""
        return f'broadcast "{message}"'
    
    @staticmethod
    def get_map_command() -> str:
        """Get command to get current map"""
        return "get map"
    
    @staticmethod
    def get_server_name_command() -> str:
        """Get command to get server name"""
        return "get name"
    
    @staticmethod
    def parse_players_response(response: str) -> list:
        """Parse the response from get players command"""
        players = []
        if not response:
            return players
        
        lines = response.strip().split('\n')
        for line in lines:
            if line.strip() and not line.startswith('Name:'):
                # Parse player info - format may vary
                # Example: "PlayerName [Team] [Role] [Steam64ID]"
                parts = line.split('\t') if '\t' in line else [line]
                if parts:
                    player_info = {
                        'name': parts[0].strip(),
                        'team': parts[1].strip() if len(parts) > 1 else '',
                        'role': parts[2].strip() if len(parts) > 2 else '',
                        'steam_id': parts[3].strip() if len(parts) > 3 else ''
                    }
                    players.append(player_info)
        
        return players
    
    @staticmethod
    def parse_map_response(response: str) -> Dict[str, Any]:
        """Parse the response from get map command"""
        map_info = {
            'name': '',
            'mode': '',
            'time_remaining': ''
        }
        
        if response:
            lines = response.strip().split('\n')
            for line in lines:
                if 'Map:' in line:
                    map_info['name'] = line.split('Map:')[1].strip()
                elif 'Mode:' in line:
                    map_info['mode'] = line.split('Mode:')[1].strip()
                elif 'Time:' in line:
                    map_info['time_remaining'] = line.split('Time:')[1].strip()
        
        return map_info

def handle_admin_command(player_id, message):
    # Logic to handle the !admin command
    # This function should create a thread in Discord and send the initial message
    pass

def send_response_to_player(player_id, response):
    # Logic to send a response back to the player in-game
    pass

def process_admin_thread_response(thread_id, response):
    # Logic to process responses from the Discord thread and send them back to the player
    pass