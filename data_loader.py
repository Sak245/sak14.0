
import pandas as pd
import logging
from typing import Optional, Dict, List, Tuple
import json
import os
from pathlib import Path
import tempfile

class DataLoader:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.bond_details = None
        self.cashflow_details = None
        self.company_insights = None
        self._chunk_size = 50000

    def set_chunk_size(self, size: int):
        """Set the chunk size for processing large files"""
        self._chunk_size = max(1000, min(size, 100000))

    def load_data(self, bond_files: List, cashflow_file, company_file, chunk_size: Optional[int] = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Dict]]:
        """Load and process all data files"""
        if chunk_size:
            self.set_chunk_size(chunk_size)

        status = {
            "bond": {"status": "not_started", "message": ""}, 
            "cashflow": {"status": "not_started", "message": ""}, 
            "company": {"status": "not_started", "message": ""}
        }

        bond_details, cashflow_details, company_insights = None, None, None

        try:
            # Process bond files
            if bond_files and any(bond_files):
                bond_details, status["bond"] = self._process_bond_files(bond_files)
                self.bond_details = bond_details

            # Process cashflow file
            if cashflow_file:
                cashflow_details, status["cashflow"] = self._process_cashflow_file(cashflow_file)
                self.cashflow_details = cashflow_details

            # Process company file
            if company_file:
                company_insights, status["company"] = self._process_company_file(company_file)
                self.company_insights = company_insights

        except Exception as e:
            self.logger.error(f"Error in load_data: {str(e)}")
            # Update any unset status
            for key in status:
                if status[key]["status"] in ["not_started", "in_progress"]:
                    status[key]["status"] = "error"
                    status[key]["message"] = "Unexpected error during processing"

        return bond_details, cashflow_details, company_insights, status

    def _process_bond_files(self, bond_files: List) -> Tuple[Optional[pd.DataFrame], Dict[str, str]]:
        """Process multiple bond files"""
        status = {"status": "in_progress", "message": ""}
        try:
            bond_dfs = []
            for i, bf in enumerate(bond_files):
                if bf is None:
                    continue

                temp_path = self._save_temp_file(bf)
                if not temp_path:
                    continue

                try:
                    # Load and validate file
                    df = self._load_and_validate_csv(
                        temp_path, 
                        ['isin', 'company_name'],
                        f"Bond file {i+1}"
                    )
                    if df is not None:
                        bond_dfs.append(df)
                finally:
                    self._cleanup_temp_file(temp_path)

            if bond_dfs:
                bond_details = pd.concat(bond_dfs, ignore_index=True)
                bond_details = bond_details.drop_duplicates(subset=['isin'], keep='first')
                self._process_json_columns(bond_details)
                status = {
                    "status": "success",
                    "message": f"Loaded {len(bond_details)} bonds"
                }
                return bond_details, status
            else:
                status = {
                    "status": "error",
                    "message": "No valid bond files processed"
                }
                return None, status

        except Exception as e:
            self.logger.error(f"Error processing bond files: {str(e)}")
            status = {
                "status": "error",
                "message": f"Error processing bond files: {str(e)}"
            }
            return None, status

    def _process_cashflow_file(self, cashflow_file) -> Tuple[Optional[pd.DataFrame], Dict[str, str]]:
        """Process cashflow file"""
        status = {"status": "in_progress", "message": ""}
        temp_path = self._save_temp_file(cashflow_file)

        if not temp_path:
            status = {
                "status": "error",
                "message": "Failed to save cashflow file"
            }
            return None, status

        try:
            df = self._load_and_validate_csv(
                temp_path,
                ['isin', 'cash_flow_date', 'cash_flow_amount'],
                "Cashflow file"
            )
            if df is not None:
                # Convert date columns
                for col in ['cash_flow_date', 'record_date']:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce')

                # Convert numeric columns
                for col in ['cash_flow_amount', 'principal_amount', 'interest_amount']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                status = {
                    "status": "success",
                    "message": f"Loaded {len(df)} cashflow records"
                }
                return df, status
            return None, {
                "status": "error",
                "message": "Failed to validate cashflow file"
            }

        except Exception as e:
            self.logger.error(f"Error processing cashflow file: {str(e)}")
            status = {
                "status": "error",
                "message": f"Error processing cashflow file: {str(e)}"
            }
            return None, status
        finally:
            self._cleanup_temp_file(temp_path)

    def _process_company_file(self, company_file) -> Tuple[Optional[pd.DataFrame], Dict[str, str]]:
        """Process company insights file"""
        status = {"status": "in_progress", "message": ""}
        temp_path = self._save_temp_file(company_file)

        if not temp_path:
            status = {
                "status": "error",
                "message": "Failed to save company file"
            }
            return None, status

        try:
            df = self._load_and_validate_csv(
                temp_path,
                ['company_name'],
                "Company file"
            )
            if df is not None:
                # Process JSON columns
                json_columns = [
                    'key_metrics', 'income_statement', 'balance_sheet',
                    'cashflow', 'lenders_profile'
                ]
                for col in json_columns:
                    if col in df.columns:
                        df[col] = df[col].apply(lambda x: 
                            json.loads(x) if isinstance(x, str) and x.strip() else {})

                status = {
                    "status": "success",
                    "message": f"Loaded {len(df)} company records"
                }
                return df, status
            return None, {
                "status": "error",
                "message": "Failed to validate company file"
            }

        except Exception as e:
            self.logger.error(f"Error processing company file: {str(e)}")
            status = {
                "status": "error",
                "message": f"Error processing company file: {str(e)}"
            }
            return None, status
        finally:
            self._cleanup_temp_file(temp_path)

    def _save_temp_file(self, file) -> Optional[str]:
        """Save uploaded file to temporary location"""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as f:
                f.write(file.getvalue())
                return f.name
        except Exception as e:
            self.logger.error(f"Error saving temporary file: {str(e)}")
            return None

    def _cleanup_temp_file(self, file_path: str) -> None:
        """Clean up temporary file"""
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            self.logger.error(f"Error cleaning up temporary file: {str(e)}")

    def _load_and_validate_csv(self, file_path: str, required_columns: List[str], file_desc: str) -> Optional[pd.DataFrame]:
        """Load and validate CSV file"""
        try:
            # Load CSV in chunks
            chunks = []
            for chunk in pd.read_csv(file_path, chunksize=self._chunk_size):
                if not chunk.empty:
                    chunks.append(chunk)

            if not chunks:
                self.logger.error(f"{file_desc} is empty")
                return None

            df = pd.concat(chunks, ignore_index=True)

            # Validate required columns
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                self.logger.error(f"Missing columns in {file_desc}: {', '.join(missing_cols)}")
                return None

            return df
        except Exception as e:
            self.logger.error(f"Error loading {file_desc}: {str(e)}")
            return None

    def _process_json_columns(self, df: pd.DataFrame) -> None:
        """Process JSON columns in DataFrame"""
        json_columns = [
            'coupon_details', 'issuer_details', 'instrument_details',
            'redemption_details', 'credit_rating_details', 'listing_details',
            'key_contact_details', 'key_documents_details'
        ]

        for col in json_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: 
                    json.loads(x) if isinstance(x, str) and x.strip() else {})

    def get_bond_details(self, isin: Optional[str] = None) -> pd.DataFrame:
        """Retrieve bond details, optionally filtered by ISIN"""
        if self.bond_details is None:
            raise ValueError("Bond data not loaded")
        if isin:
            return self.bond_details[self.bond_details['isin'] == isin]
        return self.bond_details

    def get_cashflow_details(self, isin: Optional[str] = None) -> pd.DataFrame:
        """Retrieve cashflow details, optionally filtered by ISIN"""
        if self.cashflow_details is None:
            raise ValueError("Cashflow data not loaded")
        if isin:
            return self.cashflow_details[self.cashflow_details['isin'] == isin]
        return self.cashflow_details

    def get_company_insights(self, company_name: Optional[str] = None) -> pd.DataFrame:
        """Retrieve company insights, optionally filtered by company name"""
        if self.company_insights is None:
            raise ValueError("Company data not loaded")
        if company_name:
            return self.company_insights[
                self.company_insights['company_name'].str.contains(
                    company_name, case=False, na=False
                )
            ]
        return self.company_insights

    def lookup_bond_by_isin(self, isin: str) -> Dict:
        """Look up bond details by ISIN"""
        try:
            if self.bond_details is None:
                return {"error": "Bond data not loaded"}
                
            # Try exact match
            matching_bonds = self.bond_details[self.bond_details['isin'] == isin]
            
            if matching_bonds.empty:
                # Try partial match
                matching_bonds = self.bond_details[self.bond_details['isin'].str.contains(isin, case=False, na=False)]
            
            if not matching_bonds.empty:
                bond_data = matching_bonds.iloc[0].to_dict()
                
                # Get cashflow data if available
                cashflow_data = None
                if self.cashflow_details is not None:
                    cashflow = self.cashflow_details[
                        self.cashflow_details['isin'] == matching_bonds.iloc[0]['isin']
                    ]
                    if not cashflow.empty:
                        cashflow_data = cashflow.to_dict('records')
                
                # Get company data if available
                company_data = None
                if self.company_insights is not None:
                    company = self.company_insights[
                        self.company_insights['company_name'] == matching_bonds.iloc[0]['company_name']
                    ]
                    if not company.empty:
                        company_data = company.iloc[0].to_dict()
                
                return {
                    "bond_data": bond_data,
                    "cashflow_data": cashflow_data,
                    "company_data": company_data
                }
            
            return {"error": f"No bond found with ISIN: {isin}"}
        except Exception as e:
            self.logger.error(f"Error looking up bond: {str(e)}")
            return {"error": f"Error looking up bond: {str(e)}"}
