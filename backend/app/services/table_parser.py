"""
Table parser service for extracting and classifying tables from PDFs

Handles intelligent classification of tables as:
- Capital Calls
- Distributions
- Adjustments
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import re
from sqlalchemy.orm import Session


class TableParser:
    """Parse and classify tables extracted from PDF documents"""
    
    def __init__(self):
        # Keywords for table classification
        self.capital_call_keywords = [
            'capital call', 'contribution', 'commitment', 'called', 
            'call date', 'capital contribution', 'drawdown'
        ]
        self.distribution_keywords = [
            'distribution', 'return of capital', 'dividend', 'payment',
            'distribution date', 'recallable', 'proceeds'
        ]
        self.adjustment_keywords = [
            'adjustment', 'rebalance', 'recall', 'correction',
            'capital call adjustment', 'distribution recall'
        ]
    
    def classify_table(self, table_data: List[List[str]], context: str = "") -> str:
        """
        Classify a table based on headers and content
        
        Args:
            table_data: 2D array of table cells
            context: Surrounding text context
            
        Returns:
            'capital_call', 'distribution', 'adjustment', or 'unknown'
        """
        if not table_data or len(table_data) < 2:
            return 'unknown'
        
        # Get headers (first row)
        headers = [str(cell).lower() if cell else '' for cell in table_data[0]]
        headers_text = ' '.join(headers)
        context_lower = context.lower()
        
        # Combined text for classification
        combined_text = f"{headers_text} {context_lower}"
        
        # Count keyword matches
        capital_score = sum(1 for kw in self.capital_call_keywords if kw in combined_text)
        distribution_score = sum(1 for kw in self.distribution_keywords if kw in combined_text)
        adjustment_score = sum(1 for kw in self.adjustment_keywords if kw in combined_text)
        
        # Determine table type based on scores
        max_score = max(capital_score, distribution_score, adjustment_score)
        if max_score == 0:
            return 'unknown'
        
        if capital_score == max_score:
            return 'capital_call'
        elif distribution_score == max_score:
            return 'distribution'
        elif adjustment_score == max_score:
            return 'adjustment'
        
        return 'unknown'
    
    def parse_capital_call_table(self, table_data: List[List[str]], fund_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Parse a capital call table and insert into database
        
        Args:
            table_data: 2D array of table cells
            fund_id: Fund ID
            db: Database session
            
        Returns:
            List of parsed capital call records
        """
        from app.models.transaction import CapitalCall
        
        if len(table_data) < 2:
            return []
        
        # Identify column indices
        headers = [str(cell).lower() if cell else '' for cell in table_data[0]]
        date_idx = self._find_column_index(headers, ['date', 'call date', 'transaction date'])
        amount_idx = self._find_column_index(headers, ['amount', 'capital call', 'contribution'])
        type_idx = self._find_column_index(headers, ['type', 'call type', 'call number'])
        desc_idx = self._find_column_index(headers, ['description', 'details', 'notes'])
        
        records = []
        
        # Parse data rows (skip header)
        for row in table_data[1:]:
            if not row or len(row) == 0:
                continue
            
            try:
                # Extract date
                call_date = None
                if date_idx is not None and date_idx < len(row):
                    call_date = self._parse_date(row[date_idx])
                
                # Extract amount
                amount = None
                if amount_idx is not None and amount_idx < len(row):
                    amount = self._parse_amount(row[amount_idx])
                
                # Skip row if critical fields are missing
                if not call_date or not amount or amount == 0:
                    continue
                
                # Extract optional fields
                call_type = row[type_idx] if type_idx is not None and type_idx < len(row) else None
                description = row[desc_idx] if desc_idx is not None and desc_idx < len(row) else None
                
                # Create capital call record
                capital_call = CapitalCall(
                    fund_id=fund_id,
                    call_date=call_date,
                    call_type=call_type,
                    amount=amount,
                    description=description
                )
                db.add(capital_call)
                
                records.append({
                    'fund_id': fund_id,
                    'call_date': call_date,
                    'call_type': call_type,
                    'amount': float(amount),
                    'description': description
                })
                
            except Exception as e:
                print(f"Error parsing capital call row {row}: {e}")
                continue
        
        # Commit all records
        db.commit()
        
        return records
    
    def parse_distribution_table(self, table_data: List[List[str]], fund_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Parse a distribution table and insert into database
        
        Args:
            table_data: 2D array of table cells
            fund_id: Fund ID
            db: Database session
            
        Returns:
            List of parsed distribution records
        """
        from app.models.transaction import Distribution
        
        if len(table_data) < 2:
            return []
        
        # Identify column indices
        headers = [str(cell).lower() if cell else '' for cell in table_data[0]]
        date_idx = self._find_column_index(headers, ['date', 'distribution date', 'transaction date'])
        amount_idx = self._find_column_index(headers, ['amount', 'distribution', 'payment'])
        type_idx = self._find_column_index(headers, ['type', 'distribution type'])
        recallable_idx = self._find_column_index(headers, ['recallable', 'is recallable'])
        desc_idx = self._find_column_index(headers, ['description', 'details', 'notes'])
        
        records = []
        
        # Parse data rows
        for row in table_data[1:]:
            if not row or len(row) == 0:
                continue
            
            try:
                # Extract date
                distribution_date = None
                if date_idx is not None and date_idx < len(row):
                    distribution_date = self._parse_date(row[date_idx])
                
                # Extract amount
                amount = None
                if amount_idx is not None and amount_idx < len(row):
                    amount = self._parse_amount(row[amount_idx])
                
                # Skip row if critical fields are missing
                if not distribution_date or not amount or amount == 0:
                    continue
                
                # Extract optional fields
                distribution_type = row[type_idx] if type_idx is not None and type_idx < len(row) else None
                is_recallable = False
                if recallable_idx is not None and recallable_idx < len(row):
                    is_recallable = self._parse_boolean(row[recallable_idx])
                description = row[desc_idx] if desc_idx is not None and desc_idx < len(row) else None
                
                # Create distribution record
                distribution = Distribution(
                    fund_id=fund_id,
                    distribution_date=distribution_date,
                    distribution_type=distribution_type,
                    is_recallable=is_recallable,
                    amount=amount,
                    description=description
                )
                db.add(distribution)
                
                records.append({
                    'fund_id': fund_id,
                    'distribution_date': distribution_date,
                    'distribution_type': distribution_type,
                    'is_recallable': is_recallable,
                    'amount': float(amount),
                    'description': description
                })
                
            except Exception as e:
                print(f"Error parsing distribution row {row}: {e}")
                continue
        
        # Commit all records
        db.commit()
        
        return records
    
    def parse_adjustment_table(self, table_data: List[List[str]], fund_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        Parse an adjustment table and insert into database
        
        Args:
            table_data: 2D array of table cells
            fund_id: Fund ID
            db: Database session
            
        Returns:
            List of parsed adjustment records
        """
        from app.models.transaction import Adjustment
        
        if len(table_data) < 2:
            return []
        
        # Identify column indices
        headers = [str(cell).lower() if cell else '' for cell in table_data[0]]
        date_idx = self._find_column_index(headers, ['date', 'adjustment date', 'transaction date'])
        amount_idx = self._find_column_index(headers, ['amount', 'adjustment'])
        type_idx = self._find_column_index(headers, ['type', 'adjustment type'])
        category_idx = self._find_column_index(headers, ['category'])
        desc_idx = self._find_column_index(headers, ['description', 'details', 'notes'])
        
        records = []
        
        # Parse data rows
        for row in table_data[1:]:
            if not row or len(row) == 0:
                continue
            
            try:
                # Extract date
                adjustment_date = None
                if date_idx is not None and date_idx < len(row):
                    adjustment_date = self._parse_date(row[date_idx])
                
                # Extract amount
                amount = None
                if amount_idx is not None and amount_idx < len(row):
                    amount = self._parse_amount(row[amount_idx])
                
                # Skip row if critical fields are missing
                if not adjustment_date or amount is None:
                    continue
                
                # Extract optional fields
                adjustment_type = row[type_idx] if type_idx is not None and type_idx < len(row) else None
                category = row[category_idx] if category_idx is not None and category_idx < len(row) else None
                description = row[desc_idx] if desc_idx is not None and desc_idx < len(row) else None
                
                # Determine if it's a contribution adjustment
                is_contribution_adjustment = False
                if adjustment_type and 'capital call' in adjustment_type.lower():
                    is_contribution_adjustment = True
                
                # Create adjustment record
                adjustment = Adjustment(
                    fund_id=fund_id,
                    adjustment_date=adjustment_date,
                    adjustment_type=adjustment_type,
                    category=category,
                    amount=amount,
                    is_contribution_adjustment=is_contribution_adjustment,
                    description=description
                )
                db.add(adjustment)
                
                records.append({
                    'fund_id': fund_id,
                    'adjustment_date': adjustment_date,
                    'adjustment_type': adjustment_type,
                    'category': category,
                    'amount': float(amount),
                    'is_contribution_adjustment': is_contribution_adjustment,
                    'description': description
                })
                
            except Exception as e:
                print(f"Error parsing adjustment row {row}: {e}")
                continue
        
        # Commit all records
        db.commit()
        
        return records
    
    def _find_column_index(self, headers: List[str], possible_names: List[str]) -> Optional[int]:
        """Find column index by matching possible header names"""
        for i, header in enumerate(headers):
            for name in possible_names:
                if name in header:
                    return i
        return None
    
    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse date from various formats"""
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # Common date formats
        date_formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%m-%d-%Y',
            '%d-%m-%Y',
            '%b %d, %Y',
            '%B %d, %Y',
            '%d %b %Y',
            '%d %B %Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_amount(self, amount_str: Any) -> Optional[Decimal]:
        """Parse amount from string (handles currency symbols and formatting)"""
        if not amount_str:
            return None
        
        # Convert to string and clean
        amount_str = str(amount_str).strip()
        
        # Remove currency symbols and separators
        amount_str = re.sub(r'[$€£¥,\s]', '', amount_str)
        
        # Handle parentheses as negative (accounting format)
        if amount_str.startswith('(') and amount_str.endswith(')'):
            amount_str = '-' + amount_str[1:-1]
        
        try:
            return Decimal(amount_str)
        except Exception:
            return None
    
    def _parse_boolean(self, value: Any) -> bool:
        """Parse boolean value from various representations"""
        if isinstance(value, bool):
            return value
        
        if not value:
            return False
        
        value_str = str(value).lower().strip()
        return value_str in ['yes', 'true', '1', 'y', 'recallable']
