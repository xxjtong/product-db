from app.models.category import Category, CategorySpecDefinition
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.solution import Solution, SolutionItem
from app.models.bom_template import BOMTemplate, SolutionBOMSnapshot
from app.models.quotation import Quotation, QuotationItem
from app.models.ai_models import AIConversation, AIMessage
from app.models.login_log import LoginLog
from app.models.system_setting import SystemSetting
from app.models.field_setting import FieldSetting
from app.models.ai_usage_log import AIUsageLog
from app.models.download_log import DownloadLog
from app.models.product_file import ProductFile
from app.models.user import User
from app.models.dictionary import Manufacturer, DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric
from app.models.mapping import (ProductCommMethod, ProductCommProtocol, ProductPowerSupply,
                                ProductHardwareInterface, ProductSensorCapability, ProductImage)
