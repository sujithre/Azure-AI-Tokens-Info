#!/usr/bin/env python3
"""
Azure OpenAI Token Analysis Script
Discovers Azure OpenAI/AI Services resources and exports monthly token usage to CSV
"""

import pandas as pd
from typing import List, Dict, Any, Optional
import sys
import subprocess
import json
import csv
import platform
from datetime import datetime, timedelta
from azure.identity import AzureCliCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest

def get_az_command():
    """
    Get the correct Azure CLI command for the current platform
   
    Returns:
        str: 'az.cmd' on Windows, 'az' on other platforms
    """
    return 'az.cmd' if platform.system() == 'Windows' else 'az'

def extract_model_name_from_deployment(deployment_name: str) -> str:
    """
    Extract model name from deployment name using common patterns
    Examples:
        "oai-smartncc-search-gpt-4o-mini-01" -> "gpt-4o-mini"
        "oai-smartncc-search-gpt-4o-01" -> "gpt-4o"
        "gpt-4o" -> "gpt-4o"
        "text-embedding-ada-002" -> "text-embedding-ada-002"
    """
    if not deployment_name:
        return deployment_name
   
    # Common model name patterns
    model_patterns = [
        'gpt-4o-mini',
        'gpt-4o',
        'gpt-4-turbo',
        'gpt-4',
        'gpt-35-turbo',
        'gpt-3.5-turbo',
        'text-embedding-ada-002',
        'text-embedding-3-large',
        'text-embedding-3-small',
        'text-embedding-ada',
        'o1-preview',
        'o1-mini',
        'o3-mini'
    ]
   
    # Check if deployment name contains any known model pattern
    deployment_lower = deployment_name.lower()
    for pattern in model_patterns:
        if pattern in deployment_lower:
            return pattern
   
    # If no pattern found, return original deployment name
    return deployment_name


def get_openai_resources_with_subscription_info() -> List[Dict[str, Any]]:
    """
    Get all Azure OpenAI and AIServices resources with subscription information using Resource Graph
   
    Returns:
        List[Dict[str, Any]]: List of OpenAI and AIServices resources with subscription metadata
    """
    try:
        # Create credentials using Azure CLI authentication
        credential = AzureCliCredential()
       
        # Create Resource Graph client
        client = ResourceGraphClient(credential)
       
        # Define the query to join OpenAI and AIServices resources with subscription information
        query = """
        Resources
        | where type =~ 'microsoft.cognitiveservices/accounts'
        | where kind in ('AIServices','OpenAI')
        | where sku != ''
        | project id, name, kind, subscriptionId, resourceGroup, location, tags, sku
        | join kind=inner (
            resourcecontainers
            | where type == "microsoft.resources/subscriptions"
            | project subscriptionName=name, subscriptionId
        ) on subscriptionId
        | project id, name, kind, subscriptionId, subscriptionName, resourceGroup, location,sku
        | order by subscriptionId asc
        """
       
        print("🔍 Discovering Azure OpenAI and AIServices resources with subscription info...")
       
        # Create query request
        query_request = QueryRequest(query=query)
       
        # Execute the query
        response = client.resources(query_request)
       
        # Extract data from response
        if hasattr(response, 'data') and response.data:
            return response.data
        else:
            print("No OpenAI or AIServices resources found")
            return []
           
    except Exception as e:
        print(f"Error discovering OpenAI and AIServices resources: {e}")
        return []

def get_token_data_for_resource(resource_id: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Get token data for a specific OpenAI resource using Azure CLI - CLOUD SHELL VERSION
    Gets both input (ProcessedPromptTokens) and output (GeneratedTokens) tokens
   
    Args:
        resource_id: Full Azure resource ID
        start_date: Start date for analysis
        end_date: End date for analysis
       
    Returns:
        pd.DataFrame: Combined token usage data (input + output)
    """
   
    all_data_rows = []
   
    # Query both input and output tokens
    metrics_to_query = [
        ('ProcessedPromptTokens', 'Input Tokens'),
        ('GeneratedTokens', 'Output Tokens')
    ]
   
    for metric_name, metric_description in metrics_to_query:
        print(f"  🔍 Querying {metric_description} ({metric_name})...")
       
        try:
            cmd = [
                get_az_command(), "monitor", "metrics", "list",
                "--resource", resource_id,
                "--metric", metric_name,
                "--start-time", start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "--end-time", end_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "--interval", "P1D",
                "--aggregation", "Total",
                "--filter", "ModelDeploymentName eq '*'",
                "--output", "json"
            ]
           
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
           
            if result.returncode != 0:
                print(f"    ❌ Error getting {metric_description}: {result.stderr}")
                continue
           
            # Check if stdout is empty or contains error messages
            if not result.stdout.strip():
                print(f"    ⚠️ Empty response from Azure CLI for {metric_description}")
                continue
           
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as json_err:
                print(f"    ❌ JSON parsing error for {metric_description}: {json_err}")
                continue
           
            if not data.get('value'):
                print(f"    ⚠️ No {metric_description} data found")
                continue
           
            for metric in data['value']:
                for timeseries in metric.get('timeseries', []):
                    # Extract model deployment name
                    deployment_name = "Unknown"
                    if 'metadatavalues' in timeseries:
                        for meta in timeseries['metadatavalues']:
                            if meta['name']['value'].lower() == 'modeldeploymentname':
                                deployment_name = meta['value']
                                break
                   
                    # Extract data points
                    for data_point in timeseries.get('data', []):
                        total_value = float(data_point.get('total', 0)) if data_point.get('total') is not None else 0
                        if total_value > 0:
                            all_data_rows.append({
                                'date': pd.to_datetime(data_point['timeStamp']).date(),
                                'timestamp': pd.to_datetime(data_point['timeStamp']),
                                'metric_name': metric_name,
                                'metric_type': metric_description,
                                'total': total_value,
                                'deployment_name': deployment_name
                            })
       
        except Exception as e:
            print(f"    ❌ Error processing {metric_description}: {str(e)}")
            continue
   
    if not all_data_rows:
        print(f"  ℹ️ No token usage data found for any metrics")
        return pd.DataFrame()
   
    df = pd.DataFrame(all_data_rows)
   
    # Ensure 'total' column is numeric
    if 'total' in df.columns:
        df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(0)
   
    return df

def get_deployment_info_for_resource(resource_name: str, resource_group: str, subscription_id: str = None) -> Dict[str, Dict[str, str]]:
    """
    Get deployment information to map deployment names to model names

   
    Args:
        resource_name: OpenAI resource name
        resource_group: Resource group name
        subscription_id: Optional subscription ID to set before querying
       
    Returns:
        Dict: Mapping of deployment names to model info
    """
    try:
        # Set subscription if provided
        if subscription_id:
            set_cmd = [get_az_command(), "account", "set", "--subscription", subscription_id]
            set_result = subprocess.run(set_cmd, capture_output=True, text=True, shell=False)
            if set_result.returncode != 0:
                print(f"    ⚠️ Failed to set subscription {subscription_id}: {set_result.stderr}")
       
        cmd = [
            get_az_command(), "cognitiveservices", "account", "deployment", "list",
            "--name", resource_name,
            "--resource-group", resource_group,
            "--output", "json"
        ]
       
        print(f"    🔍 Fetching deployment info for: {resource_name}")
        result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
       
        if result.returncode == 0:
            deployments = json.loads(result.stdout)
            deployment_mapping = {}
           
            for deployment in deployments:
                deployment_name = deployment.get('name', 'Unknown')
                model_name = deployment.get('properties', {}).get('model', {}).get('name', 'Unknown')
                model_version = deployment.get('properties', {}).get('model', {}).get('version', 'Unknown')
               
                deployment_mapping[deployment_name] = {
                    'model_name': model_name,
                    'model_version': model_version
                }
                print(f"      📌 Deployment: {deployment_name} → Model: {model_name}")
           
            if deployment_mapping:
                print(f"    ✅ Retrieved {len(deployment_mapping)} deployment(s)")
            else:
                print(f"    ⚠️ No deployments found in response")
            return deployment_mapping
        else:
            print(f"    ⚠️ Failed to get deployment info (return code {result.returncode})")
            print(f"    ⚠️ Error: {result.stderr}")
            return {}
       
    except json.JSONDecodeError as je:
        print(f"    ⚠️ JSON parsing error: {je}")
        print(f"    ⚠️ Response: {result.stdout[:200]}...")
        return {}
    except Exception as e:
        print(f"    ⚠️ Error getting deployment info: {e}")
        return {}

def extract_resource_info(resource_id: str) -> tuple:
    """
    Extract subscription ID, resource group, and resource name from resource ID
   
    Args:
        resource_id: Full Azure resource ID
       
    Returns:
        tuple: (subscription_id, resource_group, resource_name)
    """
    # Resource ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{name}
    parts = resource_id.split('/')
    subscription_id = parts[2] if len(parts) > 2 else ""
    resource_group = parts[4] if len(parts) > 4 else ""
    resource_name = parts[-1] if parts else ""
    return subscription_id, resource_group, resource_name

def export_to_csv(all_results: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> str:
    """
    Export results to CSV with all required columns
   
    Args:
        all_results: List of token usage data
        start_date: Analysis start date
        end_date: Analysis end date
       
    Returns:
        str: Path to exported CSV file
    """
    if not all_results:
        print("No data to export")
        return ""
   
    # Create CSV filename with timestamp
    month_year = start_date.strftime("%B_%Y")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"azure_openai_tokens_{month_year}_{timestamp}.csv"
   
    try:
        # Prepare CSV data
        csv_data = []
       
        for result in all_results:
            csv_row = {
                'ID': result.get('resource_id', ''),
                'DeploymentName': result.get('deployment_name', ''),
                'ModelName': result.get('model_name', ''),
                'Processed Inference Tokens (Sum)': int(result.get('total_tokens', 0)),
                'Month': start_date.strftime("%B %Y"),
                'Subscription Id': result.get('subscription_id', ''),
                'Subscription Name': result.get('subscription_name', ''),
                'Kind': result.get('kind', '')
            }
           
            csv_data.append(csv_row)
       
        # Write to CSV
        fieldnames = [
            'ID', 'DeploymentName', 'ModelName', 'Processed Inference Tokens (Sum)', 'Month',
            'Subscription Id', 'Subscription Name', 'Kind'
        ]
       
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)
       
        print(f"📊 CSV exported successfully: {csv_filename}")
        print(f"📈 Total rows exported: {len(csv_data)}")
       
        return csv_filename
       
    except Exception as e:
        print(f"❌ Error exporting CSV: {e}")
        return ""

def display_results(all_results: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> None:
    """
    Display consolidated token usage results and export to CSV
   
    Args:
        all_results: List of token usage data across all resources
    """
    if not all_results:
        print("No token usage data found across all OpenAI resources.")
        return
   
    # Convert to DataFrame for better display
    df = pd.DataFrame(all_results)
   
    print(f"\n📊 Token Usage Summary ({start_date.strftime('%B %Y')})")
    print("=" * 120)
   
    # Group by resource, deployment name, and model
    summary = df.groupby(['resource_name', 'deployment_name', 'model_name'])['total_tokens'].sum().reset_index()
    summary = summary.sort_values(['resource_name', 'total_tokens'], ascending=[True, False])
   
    # Display summary table
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)
   
    print(summary.to_string(index=False))
    print("=" * 120)
   
    # Display totals
    total_tokens = df['total_tokens'].sum()
    total_resources = df['resource_name'].nunique()
    total_models = df['model_name'].nunique()
   
    print(f"\n📈 Overall Summary:")
    print(f"🎯 Total Tokens: {total_tokens:,.0f}")
    print(f"🏢 OpenAI Resources: {total_resources}")
    print(f"🤖 Unique Models: {total_models}")
   
    # Export to CSV
    print(f"\n📤 Exporting results to CSV...")
    csv_file = export_to_csv(all_results, start_date, end_date)
    if csv_file:
        print(f"✅ CSV export completed: {csv_file}")
    else:
        print("❌ CSV export failed")

def test_azure_authentication():
    """
    Test Azure authentication and basic CLI functionality
    """
    print("🔍 Testing Azure CLI authentication...")
   
    try:
        # Test az account show
        cmd = [get_az_command(), "account", "show", "--output", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
       
        if result.returncode == 0:
            account_info = json.loads(result.stdout)
            print(f"✅ Authenticated as: {account_info.get('user', {}).get('name', 'Unknown')}")
            print(f"✅ Current subscription: {account_info.get('name', 'Unknown')}")
            return True
        else:
            print(f"❌ Authentication failed: {result.stderr}")
            return False
           
    except Exception as e:
        print(f"❌ Error testing authentication: {e}")
        return False

def main():
    """
    Main function to discover OpenAI resources and extract token data - COMPLETE VERSION
    """
    print("Azure OpenAI Token Analysis - COMPLETE VERSION")
    print("=" * 60)
   
    # Test authentication first
    if not test_azure_authentication():
        print("❌ Please ensure you're authenticated with 'az login'")
        return
   

    # Set date range for the analysis period
    start_date = datetime(2026, 1, 1, 0, 1, 0)
    end_date = datetime(2026, 1, 31, 23, 59, 0)
   
    print(f"📅 Analysis Period: {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}")
   
    # Check authentication
    try:
        credential = AzureCliCredential()
        # Try to get a token to verify authentication
        token = credential.get_token("https://management.azure.com/.default")
        print("✅ Azure SDK authentication successful")
    except Exception as e:
        print("❌ Azure SDK authentication failed.")
        print("Please run 'az login' first to authenticate with Azure.")
        print(f"Error: {e}")
        sys.exit(1)
   
    # Discover all OpenAI resources with subscription info
    openai_resources = get_openai_resources_with_subscription_info()
   
    if not openai_resources:
        print("❌ No Azure OpenAI or AIServices resources found.")
        return
   
    print(f"✅ Found {len(openai_resources)} Azure OpenAI/AIServices resource(s)")
   
    # Process each OpenAI resource
    all_results = []
   
    for resource in openai_resources:
        resource_id = resource['id']
        resource_name = resource['name']
        resource_kind = resource.get('kind', '')
        subscription_id = resource['subscriptionId']
        subscription_name = resource.get('subscriptionName', '')
    
       
        print(f"\n🔍 Processing: {resource_name} ({resource_kind}) (Subscription: {subscription_name})")

       
        # Extract resource info for deployment queries
        _, resource_group, _ = extract_resource_info(resource_id)
       
        # Get token data
        token_df = get_token_data_for_resource(resource_id, start_date, end_date)
       
        if token_df.empty:
            print(f"  ℹ️  No token usage data found")
            continue
       
        # Get deployment mapping (pass subscription_id to ensure correct context)
        deployment_mapping = get_deployment_info_for_resource(resource_name, resource_group, subscription_id)
       
        # Map deployment names to model names
        if deployment_mapping:
            # Create a lowercase key mapping for case-insensitive lookup
            deployment_mapping_lower = {k.lower(): v for k, v in deployment_mapping.items()}
            
            def map_to_model_name(deployment_name):
                # Try to get from deployment mapping first (case-insensitive)
                deployment_name_lower = deployment_name.lower() if deployment_name else ''
                if deployment_name_lower in deployment_mapping_lower:
                    return deployment_mapping_lower[deployment_name_lower].get('model_name', deployment_name)
                # Fallback: extract from deployment name pattern
                return extract_model_name_from_deployment(deployment_name)
           
            token_df['model_name'] = token_df['deployment_name'].apply(map_to_model_name)
        else:
            # No deployment mapping available - extract model names from deployment names
            print(f"    ⚠️ Using pattern matching to extract model names from deployment names")
            token_df['model_name'] = token_df['deployment_name'].apply(extract_model_name_from_deployment)
       
        # Aggregate results for this resource - sum both input and output tokens per deployment
        final_summary = token_df.groupby(['model_name', 'deployment_name'])['total'].sum().reset_index()
        final_summary['resource_name'] = resource_name
        final_summary['resource_id'] = resource_id
        final_summary['kind'] = resource_kind
        final_summary['subscription_id'] = subscription_id
        final_summary['subscription_name'] = subscription_name
        final_summary.rename(columns={'total': 'total_tokens'}, inplace=True)
       
        print(f"  ✅ Found {len(final_summary)} model(s) with token usage (input + output combined)")
       
        # Add to overall results
        all_results.extend(final_summary.to_dict('records'))
   
    # Display consolidated results and export CSV
    display_results(all_results, start_date, end_date)
   
    print("\n✅ Analysis complete!")

if __name__ == "__main__":
    main()