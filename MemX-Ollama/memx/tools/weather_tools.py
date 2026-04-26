import httpx
import logging
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)

class WeatherTools:
    def __init__(self):
        self.api_key = "your_api_key_here"  # 建议在.env中配置
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.timeout = 10
    
    async def get_weather(self, city: str, country: str = "CN") -> Optional[Dict[str, Any]]:
        """获取城市天气信息"""
        try:
            # 构建请求URL
            url = f"{self.base_url}/weather"
            params = {
                "q": f"{city},{country}",
                "appid": self.api_key,
                "units": "metric",  # 使用摄氏度
                "lang": "zh_cn"  # 使用中文
            }
            
            # 发送请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"成功获取{city}天气信息")
                    return self._format_weather_data(data)
                else:
                    logger.warning(f"获取天气失败: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"天气查询失败: {e}")
            return None
    
    def _format_weather_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化天气数据"""
        return {
            "城市": data.get("name"),
            "国家": data.get("sys", {}).get("country"),
            "温度": f"{data.get("main", {}).get("temp")}°C",
            "体感温度": f"{data.get("main", {}).get("feels_like")}°C",
            "湿度": f"{data.get("main", {}).get("humidity")}%",
            "气压": f"{data.get("main", {}).get("pressure")}hPa",
            "天气": data.get("weather", [{}])[0].get("description"),
            "风速": f"{data.get("wind", {}).get("speed")}m/s",
            "风向": f"{data.get("wind", {}).get("deg")}°",
            "日出": data.get("sys", {}).get("sunrise"),
            "日落": data.get("sys", {}).get("sunset")
        }
    
    async def get_forecast(self, city: str, country: str = "CN") -> Optional[Dict[str, Any]]:
        """获取天气预报"""
        try:
            # 构建请求URL
            url = f"{self.base_url}/forecast"
            params = {
                "q": f"{city},{country}",
                "appid": self.api_key,
                "units": "metric",
                "lang": "zh_cn",
                "cnt": 5  # 5天预报
            }
            
            # 发送请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"成功获取{city}天气预报")
                    return self._format_forecast_data(data)
                else:
                    logger.warning(f"获取天气预报失败: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"天气预报查询失败: {e}")
            return None
    
    def _format_forecast_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化预报数据"""
        forecasts = []
        for item in data.get("list", [])[:5]:
            forecasts.append({
                "日期": item.get("dt_txt"),
                "温度": f"{item.get("main", {}).get("temp")}°C",
                "天气": item.get("weather", [{}])[0].get("description"),
                "湿度": f"{item.get("main", {}).get("humidity")}%",
                "风速": f"{item.get("wind", {}).get("speed")}m/s"
            })
        
        return {
            "城市": data.get("city", {}).get("name"),
            "预报": forecasts
        }
