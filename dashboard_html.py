import json
import pandas as pd
import requests
from typing import Any


DEFAULT_API_BASE_URL = 'http://localhost:8000'


def fetch_job_data(
    job_id: str,
    api_base_url: str = DEFAULT_API_BASE_URL
) -> dict[str, Any]:
    """Fetch all job data from the API endpoints.

    Args:
        job_id: The job identifier to fetch data for.
        api_base_url: Base URL of the API server.

    Returns:
        Dictionary containing summary, job_status, logs, and artifact data.
    """
    data = {
        'job_id': job_id,
        'summary': None,
        'job_status': None,
        'logs': None,
        'artifact': None,
        'grid_result': None,
        'job_payload': None,
        'error': None
    }

    try:
        # Fetch summary
        resp = requests.get(f"{api_base_url}/jobs/{job_id}/summary", timeout=30)
        if resp.status_code == 200:
            data['summary'] = resp.json()
        elif resp.status_code == 404:
            data['error'] = 'Job not found'
            return data

        # Fetch job status
        resp = requests.get(f"{api_base_url}/jobs/{job_id}", timeout=30)
        if resp.status_code == 200:
            data['job_status'] = resp.json()

        # Fetch logs
        resp = requests.get(f"{api_base_url}/jobs/{job_id}/logs", timeout=30)
        if resp.status_code == 200:
            data['logs'] = resp.json()

        # Fetch original payload (signature_code, metric_code)
        resp = requests.get(f"{api_base_url}/jobs/{job_id}/payload", timeout=30)
        if resp.status_code == 200:
            data['job_payload'] = resp.json()

        # Determine job type from summary
        job_type = (data.get('summary') or {}).get('job_type', 'run')

        if job_type == 'grid_search':
            # Fetch grid result for grid search jobs
            resp = requests.get(f"{api_base_url}/jobs/{job_id}/grid-result", timeout=30)
            if resp.status_code == 200:
                data['grid_result'] = resp.json()
        else:
            # Fetch artifact for regular run jobs
            resp = requests.get(f"{api_base_url}/jobs/{job_id}/artifact", timeout=30)
            if resp.status_code == 200:
                data['artifact'] = resp.json()

    except requests.RequestException as e:
        data['error'] = f'Connection error: {str(e)}'

    return data


def generate_dashboard_html(
    job_id: str,
    api_base_url: str = DEFAULT_API_BASE_URL
) -> str:
    """Generate dashboard HTML with pre-loaded job data.

    Args:
        job_id: Job identifier. Data will be fetched and injected.
        api_base_url: Base URL of the API server.

    Returns:
        Complete HTML string with injected data.
    """
    job_data = fetch_job_data(job_id, api_base_url)

    # Convert to JSON for injection
    job_data_json = json.dumps(job_data, default=str, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>לוח בקרה DSPy</title>
    <style>
        :root {{
            /* Claude Warm Theme - Orange, Brown, Beige, Yellow */
            --primary: #C96442;
            --primary-dark: #A85232;
            --primary-light: #E08A6A;
            --primary-bg: #FDF5F2;

            --accent: #B8860B;
            --accent-light: #DAA520;
            --accent-bg: #FDF8E8;

            --secondary: #8B7355;
            --secondary-light: #A89078;
            --secondary-bg: #F5F0EB;

            --error: #C62828;
            --error-bg: #FFEBEE;
            --warning: #E67E22;
            --warning-bg: #FEF5E7;
            --success: #7D8C3E;
            --success-bg: #F4F6E8;

            --bg: #FAF8F5;
            --surface: #FFFEFA;
            --surface-hover: #F7F3ED;
            --border: #E8E2D9;
            --text-primary: #3D3229;
            --text-secondary: #7A6F63;
            --text-disabled: #C4B8A8;

            --shadow-sm: 0 1px 3px rgba(61, 50, 41, 0.08);
            --shadow-md: 0 4px 6px rgba(61, 50, 41, 0.1);
            --shadow-lg: 0 10px 20px rgba(61, 50, 41, 0.12);

            --radius-sm: 4px;
            --radius-md: 8px;
            --radius-lg: 12px;

            --transition: all 0.2s ease;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        /* Custom Scrollbars - Minimal & Elegant */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}

        ::-webkit-scrollbar-track {{
            background: transparent;
        }}

        ::-webkit-scrollbar-thumb {{
            background: rgba(138, 115, 85, 0.3);
            border-radius: 10px;
            transition: background 0.2s ease;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(138, 115, 85, 0.6);
        }}

        ::-webkit-scrollbar-corner {{
            background: transparent;
        }}

        /* Firefox */
        * {{
            scrollbar-width: thin;
            scrollbar-color: rgba(138, 115, 85, 0.3) transparent;
        }}

        body {{
            font-family: Segoe UI, Arial, Tahoma, 'Arial Hebrew', sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            line-height: 1.6;
            direction: rtl;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        /* Error Alert Banner */
        .error-banner {{
            background: var(--error-bg);
            border: 1px solid var(--error);
            border-right: 4px solid var(--error);
            border-radius: var(--radius-md);
            padding: 16px 20px;
            margin-bottom: 20px;
            display: none;
            animation: slideDown 0.3s ease;
        }}

        @keyframes slideDown {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .error-banner.show {{
            display: block;
        }}

        .error-banner-header {{
            display: flex;
            flex-direction: row-reverse;
            align-items: center;
            gap: 10px;
            font-weight: 500;
            color: var(--error);
            margin-bottom: 8px;
        }}

        .error-banner-message {{
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
        }}

        /* Status Badges */
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .status-badge::before {{
            content: "";
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}

        .status-pending {{ background: var(--surface-hover); color: var(--text-secondary); }}
        .status-pending::before {{ background: var(--text-secondary); }}
        .status-validating {{ background: var(--accent-bg); color: var(--accent); }}
        .status-validating::before {{ background: var(--accent); }}
        .status-running {{ background: var(--warning-bg); color: var(--warning); }}
        .status-running::before {{ background: var(--warning); animation: pulse 1s infinite; }}
        .status-success {{ background: var(--success-bg); color: var(--success); }}
        .status-success::before {{ background: var(--success); }}
        .status-failed {{ background: var(--error-bg); color: var(--error); }}
        .status-failed::before {{ background: var(--error); }}
        .status-cancelled {{ background: var(--secondary-bg); color: var(--secondary); }}
        .status-cancelled::before {{ background: var(--secondary); }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.6; transform: scale(0.9); }}
        }}

        /* Panels */
        .panels {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }}

        .panel {{
            background: var(--surface);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
            overflow: hidden;
            transition: box-shadow 0.2s ease;
            display: flex;
            flex-direction: column;
        }}

        .panel-full {{
            grid-column: 1 / -1;
        }}

        .panel:hover {{
            box-shadow: var(--shadow-lg);
        }}

        .panel-header {{
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: #fff;
            padding: 14px 20px;
            font-weight: 600;
            font-size: 15px;
            font-family: inherit;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .panel-content {{
            padding: 20px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }}

        @media (max-width: 1080px) {{
            .panels {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Job Timeline - Compact */
        .job-timeline {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
            padding: 12px 16px;
            background: var(--surface-hover);
            border-radius: var(--radius-md);
            flex-direction: row;
        }}

        .timeline-step {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            flex: 1;
            position: relative;
        }}

        .timeline-step:not(:first-child)::after {{
            content: "";
            position: absolute;
            top: 12px;
            left: 50%;
            width: 100%;
            height: 2px;
            background: var(--border);
            z-index: 0;
        }}

        .timeline-step.completed:not(:first-child)::after {{
            background: var(--primary);
        }}

        .timeline-step.active:not(:first-child)::after {{
            background: linear-gradient(90deg, var(--primary-light), var(--border));
        }}

        .timeline-dot {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: var(--surface);
            border: 2px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            z-index: 1;
            transition: var(--transition);
        }}

        .timeline-step.completed .timeline-dot {{
            background: var(--primary);
            border-color: var(--primary);
            color: #fff;
        }}

        .timeline-step.active .timeline-dot {{
            background: var(--primary-light);
            border-color: var(--primary-light);
            color: #fff;
            animation: pulse 1.5s infinite;
        }}

        .job-timeline.done .timeline-step .timeline-dot {{
            animation: none;
        }}

        .timeline-label {{
            font-size: 10px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}

        .timeline-step.completed .timeline-label,
        .timeline-step.active .timeline-label {{
            color: var(--text-primary);
            font-weight: 500;
        }}

        .timeline-time {{
            font-size: 9px;
            color: var(--text-disabled);
            font-family: inherit;
        }}

        /* Comparison Card */
        .comparison-card {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            direction: rtl;
            gap: 20px;
            align-items: center;
            padding: 20px;
            background: linear-gradient(135deg, var(--primary-bg), var(--accent-bg));
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            margin-bottom: 20px;
        }}

        .comparison-metric {{
            text-align: center;
        }}

        .comparison-label {{
            font-size: 11px;
            font-family: inherit;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}

        .comparison-value {{
            font-size: 32px;
            font-weight: 700;
            font-family: inherit;
        }}

        .comparison-value.baseline {{ color: var(--text-secondary); }}
        .comparison-value.optimized {{ color: var(--success); }}

        .comparison-arrow {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }}

        .comparison-arrow svg {{
            width: 32px;
            height: 32px;
            color: var(--accent);
        }}

        .comparison-improvement {{
            font-size: 14px;
            font-family: inherit;
            font-weight: 600;
            color: #fff;
            background: var(--primary);
            padding: 4px 12px;
            border-radius: 20px;
        }}

        .comparison-improvement.negative {{
            background: var(--error);
        }}

        /* Job type badge */
        .job-type-badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 10px;
            border-radius: 12px;
            letter-spacing: 0.3px;
        }}
        .job-type-badge.run {{
            background: var(--secondary-bg);
            color: var(--secondary);
        }}
        .job-type-badge.grid_search {{
            background: var(--accent-bg);
            color: var(--accent);
        }}

        /* Grid Search Results */
        .grid-results-section {{
            margin-bottom: 20px;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            overflow: hidden;
        }}

        .grid-results-header {{
            background: var(--surface-hover);
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            direction: rtl;
        }}

        .grid-results-title {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .grid-results-count {{
            font-size: 12px;
            color: var(--text-secondary);
        }}

        .grid-results-table-wrapper {{
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }}

        .grid-results-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            font-variant-numeric: tabular-nums;
        }}

        .grid-results-table th {{
            background: var(--bg);
            padding: 10px 12px;
            text-align: start;
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
            position: sticky;
            top: 0;
            z-index: 1;
        }}

        .grid-results-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}

        .grid-results-table tr:last-child td {{
            border-bottom: none;
        }}

        .grid-results-table tbody tr:hover {{
            background: var(--surface-hover);
        }}

        .grid-results-table tr.best-pair {{
            background: var(--success-bg);
            border-inline-start: 3px solid var(--success);
        }}
        .grid-results-table tr.best-pair:hover {{
            background: var(--success-bg);
        }}

        .grid-results-table tr.failed-pair {{
            background: var(--error-bg);
            color: var(--text-secondary);
        }}
        .grid-results-table tr.failed-pair:hover {{
            background: var(--error-bg);
        }}

        .grid-results-table .model-detail {{
            font-size: 11px;
            color: var(--text-secondary);
        }}

        .pair-status-badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 10px;
        }}
        .pair-status-badge.success {{ background: var(--success-bg); color: var(--success); }}
        .pair-status-badge.failed {{ background: var(--error-bg); color: var(--error); }}
        .pair-status-badge.best {{ background: var(--accent-bg); color: var(--accent); }}

        /* Summary Groups */
        .summary-groups {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .summary-group {{
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            overflow: hidden;
        }}

        .summary-group-header {{
            background: var(--surface-hover);
            padding: 10px 16px;
            font-weight: 600;
            font-size: 13px;
            color: var(--text-primary);
        }}


        .summary-group-content {{
            display: block;
        }}

        /* Summary Table */
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .summary-table tr {{
            border-bottom: 1px solid var(--border);
            transition: var(--transition);
        }}

        .summary-table tr:last-child {{
            border-bottom: none;
        }}

        .summary-table tr:hover {{
            background: var(--surface-hover);
        }}

        .summary-table td {{
            padding: 10px 16px;
            vertical-align: top;
        }}

        .summary-table td:first-child {{
            width: 130px;
            font-weight: 500;
            color: var(--text-secondary);
            position: relative;
        }}

        .summary-table td:last-child {{
            color: var(--text-primary);
            word-break: break-word;
        }}

        .summary-table .mono {{
            font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
            font-size: 12px;
            background: var(--surface-hover);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            color: var(--primary);
        }}

        .copyable {{
            cursor: pointer;
            transition: var(--transition);
        }}

        .copyable:hover {{
            background: var(--primary-bg);
        }}

        .copyable:active {{
            transform: scale(0.98);
        }}

        .copy-feedback {{
            position: fixed;
            background: var(--text-primary);
            color: var(--surface);
            padding: 10px 14px;
            border-radius: var(--radius-md);
            font-size: 13px;
            line-height: 1.5;
            z-index: 1001;
            opacity: 0;
            visibility: hidden;
            transform: translateX(-50%) scale(0.95);
            transition: opacity 0.2s ease-out, visibility 0.2s, transform 0.2s ease-out;
            box-shadow: var(--shadow-lg);
            pointer-events: none;
            direction: rtl;
            text-align: right;
        }}

        .copy-feedback.show {{
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) scale(1);
        }}

        /* Parameter with info tooltip */
        .param-label {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}

        .param-info {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--border);
            color: var(--text-secondary);
            font-size: 10px;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }}

        .param-label:hover .param-info {{
            background: var(--primary);
            color: #fff;
        }}

        /* Tooltip */
        .tooltip {{
            position: fixed;
            max-width: 360px;
            background: var(--text-primary);
            color: var(--surface);
            padding: 14px 18px;
            border-radius: var(--radius-md);
            font-size: 13px;
            line-height: 1.7;
            z-index: 1000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s, visibility 0.2s;
            box-shadow: var(--shadow-lg);
            pointer-events: none;
            direction: rtl;
            text-align: right;
        }}

        .tooltip.visible {{
            opacity: 1;
            visibility: visible;
        }}

        .tooltip-title {{
            font-weight: 600;
            margin-bottom: 8px;
            color: #fff;
            font-size: 14px;
            border-bottom: 1px solid rgba(255,255,255,0.2);
            padding-bottom: 8px;
        }}

        .tooltip-desc {{
            color: rgba(255,255,255,0.9);
        }}

        .tooltip .en {{
            direction: ltr;
            unicode-bidi: embed;
            font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace;
            background: rgba(255,255,255,0.15);
            padding: 1px 5px;
            border-radius: 3px;
            font-size: 12px;
        }}


        /* Progress Section */
        .progress-section {{
            margin-bottom: 24px;
            padding: 20px;
            background: var(--surface-hover);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
        }}

        .progress-top {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 14px;
            direction: rtl;
        }}

        .progress-percent {{
            font-size: 28px;
            font-weight: 700;
            font-family: inherit;
            color: var(--primary);
            min-width: 72px;
            text-align: center;
            line-height: 1;
        }}

        .progress-bar-container {{
            flex: 1;
            background: var(--border);
            border-radius: 6px;
            height: 8px;
            overflow: hidden;
        }}

        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, var(--primary-dark), var(--primary), var(--primary-light));
            border-radius: 6px;
            transition: width 0.5s ease;
            position: relative;
        }}

        .progress-bar::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg,
                rgba(255,255,255,0) 0%,
                rgba(255,255,255,0.2) 50%,
                rgba(255,255,255,0) 100%);
            animation: shimmer 2s infinite;
        }}

        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}

        .progress-section.done .progress-bar::after {{
            animation: none;
            display: none;
        }}

        .progress-stats {{
            display: flex;
            gap: 24px;
            font-size: 12px;
        }}

        .progress-stat {{
            display: flex;
            align-items: center;
            gap: 5px;
            direction: rtl;
        }}

        .progress-stat-label {{
            color: var(--text-disabled);
        }}

        .progress-stat-value {{
            font-weight: 600;
            color: var(--text-primary);
            direction: ltr;
        }}

        /* Logs Panel */
        .logs-panel {{
        }}

        .logs-header {{
            margin-bottom: 16px;
        }}

        .logs-header-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            gap: 16px;
            flex-wrap: wrap;
        }}

        .logs-count {{
            padding: 8px 16px;
            background: var(--surface-hover);
            border-radius: var(--radius-md);
            font-size: 14px;
            font-weight: 500;
            color: var(--text-secondary);
        }}

        .logs-controls {{
            display: flex;
            flex-direction: row-reverse;
            gap: 8px;
            align-items: center;
        }}

        .logs-controls input {{
            padding: 8px 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            font-size: 13px;
            font-family: inherit;
            background: var(--surface);
            color: var(--text-primary);
            min-width: 200px;
            text-align: right;
        }}

        .logs-controls select {{
            padding: 8px 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            font-size: 13px;
            font-family: inherit;
            background: var(--surface);
            color: var(--text-primary);
        }}

        .logs-container {{
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            font-family: inherit;
            font-size: 12px;
            overflow: hidden;
        }}

        .logs-table-header {{
            display: grid;
            grid-template-columns: 150px 80px 180px 1fr;
            direction: rtl;
            background: var(--surface-hover);
            border-bottom: 2px solid var(--border);
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
        }}

        .logs-table-header span {{
            padding: 10px 12px;
        }}

        .logs-table-body {{
            height: 320px;
            overflow-y: auto;
            overscroll-behavior: contain;
        }}

        .log-entry {{
            display: grid;
            grid-template-columns: 150px 80px 180px 1fr;
            direction: rtl;
            border-bottom: 1px solid var(--border);
            transition: var(--transition);
            align-items: start;
        }}

        .log-entry:last-child {{
            border-bottom: none;
        }}

        .log-entry:hover {{
            background: var(--surface-hover);
        }}

        .log-entry > span {{
            padding: 10px 12px;
            border-left: 1px solid var(--border);
        }}

        .log-entry > span:last-child {{
            border-left: none;
        }}

        .log-timestamp {{
            color: var(--text-secondary);
            font-size: 11px;
            direction: ltr;
            text-align: right;
        }}

        .log-level {{
            font-weight: 600;
            text-align: center;
        }}

        .log-level.DEBUG {{ color: var(--text-secondary); }}
        .log-level.INFO {{ color: var(--accent); }}
        .log-level.WARNING {{ color: var(--warning); }}
        .log-level.ERROR {{ color: var(--error); }}

        .log-logger {{
            color: var(--text-secondary);
            font-size: 11px;
            direction: ltr;
            text-align: right;
        }}

        .log-message {{
            color: var(--text-primary);
            word-break: break-word;
            direction: ltr;
            text-align: right;
        }}

        /* Empty State */
        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }}

        /* Split Fractions Display */
        .split-fractions-display {{
            display: inline-flex;
            flex-direction: row;
            gap: 8px;
            direction: rtl;
        }}

        .split-fraction-item {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: var(--accent-bg);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-family: inherit;
            white-space: nowrap;
        }}

        .split-fraction-item .label {{
            color: var(--text-secondary);
            font-weight: 400;
        }}

        .split-fraction-item .value {{
            font-family: inherit;
            font-weight: 600;
            color: var(--accent);
            direction: ltr;
        }}

        /* Optimized Prompt Section */

        /* Code Tiles (Signature & Metric) */
        .code-tile {{
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            overflow: hidden;
            margin-bottom: 12px;
        }}

        .code-tile:last-child {{
            margin-bottom: 0;
        }}

        .code-tile-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 14px;
            background: var(--accent-bg);
            border-bottom: 1px solid var(--border);
            direction: ltr;
        }}

        .code-tile-label {{
            font-size: 12px;
            font-weight: 700;
            color: var(--primary);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}

        .code-tile-copy {{
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-secondary);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            transition: var(--transition);
        }}

        .code-tile-copy:hover {{
            background: var(--surface-hover);
            color: var(--primary);
        }}

        .code-block {{
            background: #faf8f5;
            padding: 14px 16px;
            font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
            font-size: 12.5px;
            line-height: 1.7;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 300px;
            overflow-y: auto;
            overscroll-behavior: contain;
            direction: ltr;
            text-align: left;
            margin: 0;
            color: #1e1e1e;
        }}

        .code-block .kw {{ color: #0550ae; }}
        .code-block .str {{ color: #a45a28; }}
        .code-block .cls {{ color: #117a65; }}
        .code-block .fn {{ color: #6f42c1; }}
        .code-block .cmt {{ color: #6a737d; font-style: italic; }}
        .code-block .dec {{ color: #9a3568; }}
        .code-block .op {{ color: #383838; }}

        /* Kwargs Display */
        .kwargs-display {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            direction: rtl;
        }}

        .kwarg-item {{
            background: var(--accent-bg);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
            transition: var(--transition);
        }}

        .kwarg-item:hover {{
            background: var(--accent-light);
        }}

        .kwarg-item .key {{
            color: var(--text-secondary);
            font-family: inherit;
            direction: ltr;
        }}

        .kwarg-item .value {{
            color: var(--accent);
            font-family: inherit;
            font-weight: 600;
            direction: ltr;
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .log-entry {{ grid-template-columns: 1fr; gap: 4px; }}
            .header-controls input {{ width: 100%; }}
            .comparison-card {{ grid-template-columns: 1fr; text-align: center; }}
            .grid-results-table {{ font-size: 11px; }}
            .grid-results-table th, .grid-results-table td {{ padding: 6px 8px; }}
            .job-timeline {{ flex-wrap: wrap; gap: 16px; }}
            .header-top {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
    <div class="container">

        <!-- Error Banner -->
        <div class="error-banner" id="errorBanner">
            <div class="error-banner-header">
                <span id="errorBannerTitle">המשימה נכשלה</span>
            </div>
            <div class="error-banner-message" id="errorBannerMessage"></div>
        </div>

        <!-- Main Panels -->
        <div class="panels" id="mainPanels">
            <!-- Configuration Summary -->
            <div class="panel panel-full">
                <div class="panel-header">
                    <span>פרטי המשימה</span>
                </div>
                <div class="panel-content">
                    <!-- Job Timeline -->
                    <div class="job-timeline" id="jobTimeline">
                        <div class="timeline-step" data-step="pending">
                            <div class="timeline-dot">1</div>
                            <div class="timeline-label">ממתין</div>
                            <div class="timeline-time" id="pendingTime">--</div>
                        </div>
                        <div class="timeline-step" data-step="validating">
                            <div class="timeline-dot">2</div>
                            <div class="timeline-label">מאמת</div>
                            <div class="timeline-time" id="validatingTime">--</div>
                        </div>
                        <div class="timeline-step" data-step="running">
                            <div class="timeline-dot">3</div>
                            <div class="timeline-label">רץ</div>
                            <div class="timeline-time" id="runningTime">--</div>
                        </div>
                        <div class="timeline-step" data-step="done">
                            <div class="timeline-dot">4</div>
                            <div class="timeline-label">הושלם</div>
                            <div class="timeline-time" id="doneTime">--</div>
                        </div>
                    </div>

                    <!-- Summary Groups -->
                    <div class="summary-groups" id="summaryGroups"></div>

                    <!-- Tooltip element -->
                    <div class="tooltip" id="paramTooltip"></div>
                    <!-- Copy feedback -->
                    <div class="copy-feedback" id="copyFeedback">הועתק!</div>
                </div>
            </div>

            <!-- Progress Visualization -->
            <div class="panel">
                <div class="panel-header"><span>תוצאות השיפור</span></div>
                <div class="panel-content">
                    <!-- Progress Bar + Stats -->
                    <div class="progress-section" id="progressSection">
                        <div class="progress-top">
                            <span class="progress-percent" id="progressPercent">0%</span>
                            <div class="progress-bar-container">
                                <div class="progress-bar" id="progressBar" style="width: 0%"></div>
                            </div>
                        </div>
                        <div class="progress-stats">
                            <div class="progress-stat">
                                <span class="progress-stat-label">שלב</span>
                                <span class="progress-stat-value" id="progressStep">--</span>
                            </div>
                            <div class="progress-stat">
                                <span class="progress-stat-label">זמן לשלב</span>
                                <span class="progress-stat-value" id="progressRate">--</span>
                            </div>
                            <div class="progress-stat">
                                <span class="progress-stat-label">זמן משוער</span>
                                <span class="progress-stat-value" id="progressEta">--</span>
                            </div>
                        </div>
                    </div>

                    <!-- Comparison Card -->
                    <div class="comparison-card" id="comparisonCard">
                        <div class="comparison-metric">
                            <div class="comparison-label">ציון התחלתי (בדיקה)</div>
                            <div class="comparison-value baseline" id="baselineScore">--</div>
                        </div>
                        <div class="comparison-arrow">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M19 12H5M12 5l-7 7 7 7"/>
                            </svg>
                            <div class="comparison-improvement" id="improvement">+0%</div>
                        </div>
                        <div class="comparison-metric">
                            <div class="comparison-label">ציון משופר (בדיקה)</div>
                            <div class="comparison-value optimized" id="optimizedScore">--</div>
                        </div>
                    </div>

                    <!-- Grid Search Results Table -->
                    <div class="grid-results-section" id="gridResultsSection">
                        <div class="grid-results-header">
                            <span class="grid-results-title">תוצאות לפי זוג מודלים</span>
                            <span class="grid-results-count" id="gridPairsCount"></span>
                        </div>
                        <div class="grid-results-table-wrapper">
                            <table class="grid-results-table" dir="rtl">
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>מודל יצירה</th>
                                        <th>מודל רפלקציה</th>
                                        <th>בסיס</th>
                                        <th>משופר</th>
                                        <th>שיפור</th>
                                        <th>סטטוס</th>
                                    </tr>
                                </thead>
                                <tbody id="gridResultsBody"></tbody>
                            </table>
                        </div>
                    </div>

                </div>
            </div>

            <!-- Signature & Metric Panel -->
            <div class="panel" id="codePanel">
                <div class="panel-header">
                    <span>הגדרת המשימה (Signature & Metric)</span>
                </div>
                <div class="panel-content">
                    <div id="signatureSection" class="code-tile" style="display: none;">
                        <div class="code-tile-header">
                            <span class="code-tile-label">Signature</span>
                            <button class="code-tile-copy" onclick="copyCode('signatureCode', this)" title="העתק">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                            </button>
                        </div>
                        <pre class="code-block" id="signatureCode"></pre>
                    </div>
                    <div id="metricSection" class="code-tile" style="display: none;">
                        <div class="code-tile-header">
                            <span class="code-tile-label">Metric</span>
                            <button class="code-tile-copy" onclick="copyCode('metricCode', this)" title="העתק">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                            </button>
                        </div>
                        <pre class="code-block" id="metricCode"></pre>
                    </div>
                    <div id="codeEmptyState" class="empty-state">
                        <div>קוד לא זמין</div>
                    </div>
                </div>
            </div>

            <!-- Optimized Prompt Panel -->
            <div class="panel panel-full prompt-panel" id="promptPanel">
                <div class="panel-header">
                    <span>ההוראות המשופרות</span>
                </div>
                <div class="panel-content">
                    <div id="promptSection" class="code-tile">
                        <div class="code-tile-header">
                            <span class="code-tile-label">Optimized Prompt</span>
                            <button class="code-tile-copy" id="copyPromptBtn" onclick="copyPrompt()" title="העתק">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                            </button>
                        </div>
                        <pre class="code-block" id="promptContent"></pre>
                    </div>
                    <div id="promptEmptyState" class="empty-state">
                        <div>הנתונים יופיעו לאחר סיום השיפור</div>
                    </div>
                </div>
            </div>

            <!-- Logs Panel -->
            <div class="panel panel-full logs-panel">
                <div class="panel-header">
                    <span>יומן פעילות</span>
                </div>
                <div class="panel-content">
                    <div class="logs-header">
                        <div class="logs-header-row">
                            <div class="logs-controls">
                                <input type="text" id="logSearch" placeholder="חיפוש..." oninput="filterLogs()" />
                                <select id="logLevelFilter" onchange="filterLogs()">
                                    <option value="">כל הרמות</option>
                                    <option value="DEBUG">DEBUG</option>
                                    <option value="INFO">INFO</option>
                                    <option value="WARNING">WARNING</option>
                                    <option value="ERROR">ERROR</option>
                                </select>
                                <select id="logTimeFilter" onchange="filterLogs()">
                                    <option value="">כל הזמן</option>
                                    <option value="5">5 דקות אחרונות</option>
                                    <option value="30">30 דקות אחרונות</option>
                                    <option value="60">שעה אחרונה</option>
                                </select>
                            </div>
                            <div class="logs-count" id="logsCount">0 רשומות</div>
                        </div>
                    </div>
                    <div class="logs-container" id="logsContainer">
                        <div class="logs-table-header">
                            <span>זמן</span>
                            <span>סוג</span>
                            <span>מקור</span>
                            <span>הודעה</span>
                        </div>
                        <div class="logs-table-body" id="logsTableBody">
                            <div class="empty-state">
                                <div>אין פעילות עדיין</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

    </div>

    <script>
        // Configuration
        const API_BASE_URL = 'http://localhost:8000';

        // Injected data from Python (if available)
        const INJECTED_DATA = {job_data_json};

        // Encapsulated dashboard state
        const DashboardState = {{
            jobId: null,
            logs: [],
            progressData: [],
            metricsData: [],
            optimizerType: null,

            setJobId(id) {{ this.jobId = id; }},
            setLogs(logs) {{ this.logs = logs || []; }},
            setProgressData(data) {{ this.progressData = data || []; }},
            setMetricsData(data) {{ this.metricsData = data || []; }},
            setOptimizerType(type) {{ this.optimizerType = type; }},
            clear() {{
                this.jobId = null;
                this.logs = [];
                this.progressData = [];
                this.metricsData = [];
                this.optimizerType = null;
            }}
        }};

        // Legacy aliases for compatibility
        let currentJobId = null;
        let allLogs = [];

        // Status translations
        const statusTranslations = {{
            'pending': 'ממתין',
            'validating': 'מאמת',
            'running': 'רץ',
            'success': 'הצליח',
            'failed': 'נכשל',
            'cancelled': 'בוטל'
        }};

        // Parameter explanations
        const paramExplanations = {{
            'job_id': {{
                title: 'מזהה משימה',
                desc: 'מספר ייחודי לזיהוי המשימה שלך.'
            }},
            'message': {{
                title: 'סטטוס נוכחי',
                desc: 'מה קורה כרגע - באיזה שלב נמצא התהליך.'
            }},
            'job_type': {{
                title: 'סוג משימה',
                desc: '<span class="en">Run</span> - הרצה בודדת עם מודל אחד.<br><span class="en">Grid Search</span> - סריקת זוגות מודלים למציאת השילוב הטוב ביותר.'
            }},
            'metric_name': {{
                title: 'מדד הערכה',
                desc: 'הפונקציה שמודדת את איכות התוצאות. ציון גבוה יותר = תוצאה טובה יותר.'
            }},
            'module': {{
                title: 'סוג התבנית',
                desc: 'איך המערכת עונה על שאלות:<br><br>• <span class="en">Predict</span> - תשובה ישירה<br>• <span class="en">ChainOfThought</span> - חושב צעד-צעד לפני התשובה'
            }},
            'optimizer': {{
                title: 'שיטת השיפור',
                desc: 'איך המערכת מחפשת את הנוסח הטוב ביותר:<br>• <span class="en">MIPROv2</span> - בודק שילובים שונים של הוראות ודוגמאות<br>• <span class="en">GEPA</span> - לומד מטעויות ומשתפר בהדרגה'
            }},
            'dataset_rows': {{
                title: 'מספר דוגמאות',
                desc: 'כמה דוגמאות יש לאימון. יותר דוגמאות = תוצאות טובות יותר.'
            }},
            'shuffle': {{
                title: 'ערבוב',
                desc: 'האם לערבב את סדר הדוגמאות באקראי. מומלץ להשאיר פעיל.'
            }},
            'seed': {{
                title: 'מספר התחלתי',
                desc: 'מספר לשליטה באקראיות. שימוש באותו מספר יחזור על אותן תוצאות.'
            }},
            'split_fractions': {{
                title: 'חלוקת הדוגמאות',
                desc: 'איך הדוגמאות מתחלקות:<br><br>• אימון - ללמידה<br>• אימות - לבדיקה תוך כדי<br>• בדיקה - להערכה סופית'
            }},
            'username': {{
                title: 'שם משתמש',
                desc: 'המשתמש שהגיש את המשימה.'
            }},
            'model_name': {{
                title: 'מודל שפה',
                desc: 'המודל הראשי שמשמש לאופטימיזציה.'
            }},
            'reflection_model_name': {{
                title: 'מודל רפלקציה',
                desc: 'מודל נפרד שמנתח טעויות ומציע שיפורים (נדרש עבור GEPA).'
            }},
            'module_kwargs': {{
                title: 'הגדרות מודול',
                desc: 'פרמטרים נוספים שהועברו למודול.'
            }},
            'elapsed': {{
                title: 'זמן שעבר',
                desc: 'כמה זמן לקח התהליך.'
            }},
            'optimizer_kwargs': {{
                title: 'הגדרות השיפור',
                desc: 'אפשרויות נוספות לתהליך השיפור.'
            }},
            'compile_kwargs': {{
                title: 'הגדרות נוספות',
                desc: 'הגדרות טכניות נוספות.'
            }}
        }};

        // Kwarg explanations for optimizer and compile kwargs
        const kwargExplanations = {{
            // MIPROv2 optimizer kwargs
            'auto': {{
                title: 'רמת חיפוש',
                desc: 'כמה יסודי החיפוש:<br>• <span class="en">light</span> - מהיר<br>• <span class="en">medium</span> - מאוזן<br>• <span class="en">heavy</span> - יסודי'
            }},
            'num_candidates': {{
                title: 'כמות אפשרויות',
                desc: 'כמה נוסחים שונים לנסות. יותר = סיכוי למצוא נוסח טוב יותר.'
            }},
            'num_trials': {{
                title: 'מספר ניסיונות',
                desc: 'כמה שילובים שונים לבדוק.'
            }},
            'max_bootstrapped_demos': {{
                title: 'דוגמאות אוטומטיות',
                desc: 'כמה דוגמאות שהמערכת יוצרת לבד.'
            }},
            'max_labeled_demos': {{
                title: 'דוגמאות מהנתונים',
                desc: 'כמה דוגמאות לקחת מהנתונים שלך.'
            }},
            'minibatch_size': {{
                title: 'גודל קבוצה',
                desc: 'כמה דוגמאות לבדוק בכל פעם. קטן = מהיר יותר.'
            }},
            'minibatch': {{
                title: 'בדיקה חלקית',
                desc: 'האם לבדוק רק חלק מהדוגמאות בכל סבב (מהיר יותר).'
            }},
            'requires_permission_to_run': {{
                title: 'דורש אישור',
                desc: 'האם לבקש אישור לפני התחלת התהליך.'
            }},
            // GEPA optimizer kwargs
            'max_iterations': {{
                title: 'מקסימום סבבים',
                desc: 'כמה פעמים המערכת תנסה לשפר.'
            }},
            'patience': {{
                title: 'סבלנות',
                desc: 'כמה סבבים להמתין בלי שיפור לפני שעוצרים.'
            }},
            'threshold': {{
                title: 'סף שיפור',
                desc: 'השיפור המינימלי הנדרש כדי להמשיך.'
            }},
            // Compile kwargs
            'trainset': {{
                title: 'דוגמאות לאימון',
                desc: 'הדוגמאות שמשמשות ללמידה.'
            }},
            'valset': {{
                title: 'דוגמאות לבדיקה',
                desc: 'הדוגמאות שמשמשות לבחירת התוצאה הטובה ביותר.'
            }},
            'num_threads': {{
                title: 'מקביליות',
                desc: 'כמה בדיקות לעשות במקביל (מהיר יותר).'
            }},
            'display_progress': {{
                title: 'הצג התקדמות',
                desc: 'האם להציג פס התקדמות.'
            }},
            'display_table': {{
                title: 'הצג טבלה',
                desc: 'האם להציג טבלת תוצאות.'
            }}
        }};

        // Current optimizer type
        let currentOptimizerType = null;

        // Initialize on load
        document.addEventListener('DOMContentLoaded', function() {{
            if (INJECTED_DATA && !INJECTED_DATA.error) {{
                currentJobId = INJECTED_DATA.job_id;
                displayData(INJECTED_DATA);
            }} else if (INJECTED_DATA && INJECTED_DATA.error) {{
                showJobError(INJECTED_DATA.error);
            }}
        }});

        function displayData(data) {{
            const jobType = data.summary?.job_type || 'run';

            // Extract extra fields from detail response into summary for display
            const metricName = jobType === 'grid_search'
                ? data.job_status?.grid_result?.metric_name
                : data.job_status?.result?.metric_name;
            if (metricName && data.summary) data.summary._metric_name = metricName;

            const splitCounts = jobType === 'grid_search'
                ? data.job_status?.grid_result?.split_counts
                : data.job_status?.result?.split_counts;
            if (splitCounts && data.summary) data.summary._split_counts = splitCounts;

            // Pass best pair index so summary can resolve exact model configs
            if (jobType === 'grid_search' && data.grid_result?.best_pair && data.summary) {{
                data.summary._best_pair_index = data.grid_result.best_pair.pair_index;
            }}

            if (data.summary) {{
                updateSummaryPanel(data.summary);
                updateTimeline(data.summary);
            }}

            const summaryStatus = data.summary?.status;
            updateProgressPanel(data.job_status || {{}}, summaryStatus);
            updateComparisonCard(data.job_status || {{}}, jobType);

            if (data.logs) updateLogsPanel(data.logs);

            if (jobType === 'grid_search') {{
                document.getElementById('gridResultsSection').style.display = '';
                updateGridResultsPanel(data.grid_result, data.summary);
            }} else {{
                // Grid table is not relevant for single-run jobs
                document.getElementById('gridResultsSection').style.display = 'none';
                updatePromptPanel(data.artifact);
            }}

            // Populate signature & metric code panel
            updateCodePanel(data.job_payload);

            if (data.summary?.status === 'failed') {{
                showJobError(data.summary.message, 'המשימה נכשלה');
            }} else {{
                hideJobError();
            }}

        }}

        function updateTimeline(data) {{
            const timeline = document.getElementById('jobTimeline');
            const steps = ['pending', 'validating', 'running', 'done'];
            const statusMap = {{
                'pending': 0,
                'validating': 1,
                'running': 2,
                'success': 3,
                'failed': 3,
                'cancelled': 3
            }};

            const currentIndex = statusMap[data.status] || 0;
            const isFinished = ['success', 'failed', 'cancelled'].includes(data.status);
            timeline.classList.toggle('done', isFinished);

            const doneStep = document.querySelector('[data-step="done"]');
            const doneLabel = doneStep.querySelector('.timeline-label');
            if (data.status === 'cancelled') {{
                doneLabel.textContent = 'בוטל';
            }} else if (data.status === 'failed') {{
                doneLabel.textContent = 'נכשל';
            }} else {{
                doneLabel.textContent = 'הושלם';
            }}

            steps.forEach((step, i) => {{
                const el = document.querySelector(`[data-step="${{step}}"]`);
                el.classList.remove('completed', 'active');
                if (i < currentIndex) {{
                    el.classList.add('completed');
                }} else if (i === currentIndex) {{
                    el.classList.add(isFinished ? 'completed' : 'active');
                }}
            }});

            document.getElementById('pendingTime').textContent =
                data.created_at ? formatTime(data.created_at) : '--';
            document.getElementById('runningTime').textContent =
                data.started_at ? formatTime(data.started_at) : '--';
            document.getElementById('doneTime').textContent =
                data.completed_at ? formatTime(data.completed_at) : '--';
        }}

        function formatModelLabel(model) {{
            if (typeof model === 'string') return `<span class="mono">${{escapeHtml(model)}}</span>`;
            const name = model.name || '--';
            const parts = [];
            if (model.temperature !== undefined) parts.push('temp=' + model.temperature);
            if (model.max_tokens) parts.push('max_tokens=' + model.max_tokens);
            if (model.top_p !== undefined && model.top_p !== null) parts.push('top_p=' + model.top_p);
            if (parts.length === 0) return `<span class="mono">${{escapeHtml(name)}}</span>`;
            return `<span class="mono">${{escapeHtml(name)}}</span> <span class="model-detail">(${{escapeHtml(parts.join(', '))}})</span>`;
        }}

        function findModelConfig(modelName, configList) {{
            if (!configList) return null;
            for (const m of configList) {{
                if (typeof m === 'object' && m.name === modelName) return m;
            }}
            return null;
        }}

        function updateSummaryPanel(data) {{
            currentOptimizerType = detectOptimizerType(data.optimizer_name);
            const jobType = data.job_type || 'run';

            const taskItems = [
                {{ key: 'job_id', label: 'מזהה', value: data.job_id, mono: true, copyable: true }},
                {{ key: 'message', label: 'סטטוס', value: data.message || '--' }},
                {{ key: 'elapsed', label: 'זמן', value: data.elapsed_seconds ? formatDuration(data.elapsed_seconds) : '--' }},
            ];
            if (data.username) taskItems.push({{ key: 'username', label: 'משתמש', value: data.username }});
            taskItems.push({{ key: 'job_type', label: 'סוג', value: `<span class="job-type-badge ${{jobType}}">${{jobType === 'grid_search' ? 'Grid Search' : 'Run'}}</span>`, isHtml: true }});

            const optimizationItems = [
                {{ key: 'module', label: 'מודול', value: data.module_name || '--', mono: true }},
                {{ key: 'optimizer', label: 'אופטימייזר', value: data.optimizer_name || '--', mono: true }},
            ];
            if (data._metric_name) {{
                optimizationItems.push({{ key: 'metric_name', label: 'שם מדד', value: data._metric_name, mono: true }});
            }}

            if (jobType === 'grid_search') {{
                // Grid search: show model lists with full settings
                if (data.generation_models) {{
                    const labels = data.generation_models.map(m => formatModelLabel(m)).join('<br>');
                    optimizationItems.push({{ key: 'model_name', label: 'מודלי יצירה', value: labels, isHtml: true }});
                }}
                if (data.reflection_models) {{
                    const labels = data.reflection_models.map(m => formatModelLabel(m)).join('<br>');
                    optimizationItems.push({{ key: 'reflection_model_name', label: 'מודלי רפלקציה', value: labels, isHtml: true }});
                }}
                const total = data.total_pairs || 0;
                const completed = data.completed_pairs || 0;
                const failed = data.failed_pairs || 0;
                optimizationItems.push({{ key: 'dataset_rows', label: 'זוגות', value: `${{completed}}/${{total}} הושלמו${{failed > 0 ? `, ${{failed}} נכשלו` : ''}}` }});
                if (data.best_pair_label) {{
                    // Use pair index to resolve exact model configs from the grid
                    const genConfigs = data.generation_models || [];
                    const refConfigs = data.reflection_models || [];
                    const pairIdx = data._best_pair_index;
                    let bestLabel = data.best_pair_label;
                    if (pairIdx != null && genConfigs.length > 0 && refConfigs.length > 0) {{
                        const numRef = refConfigs.length;
                        const genIdx = Math.floor(pairIdx / numRef);
                        const refIdx = pairIdx % numRef;
                        const genCfg = genConfigs[genIdx] || genConfigs[0];
                        const refCfg = refConfigs[refIdx] || refConfigs[0];
                        bestLabel = formatModelLabel(genCfg) + ' + ' + formatModelLabel(refCfg);
                    }}
                    optimizationItems.push({{ key: 'model_name', label: 'זוג מנצח', value: bestLabel, isHtml: true }});
                }}
            }} else {{
                // Regular run: show model names
                if (data.model_name) optimizationItems.push({{ key: 'model_name', label: 'מודל', value: data.model_name, mono: true }});
                if (data.reflection_model_name) optimizationItems.push({{ key: 'reflection_model_name', label: 'מודל רפלקציה', value: data.reflection_model_name, mono: true }});
                if (data.prompt_model_name) optimizationItems.push({{ key: 'model_name', label: 'מודל פרומפט', value: data.prompt_model_name, mono: true }});
                if (data.task_model_name) optimizationItems.push({{ key: 'model_name', label: 'מודל משימה', value: data.task_model_name, mono: true }});
            }}

            optimizationItems.push({{ key: 'optimizer_kwargs', label: 'פרמטרים', value: formatKwargs(data.optimizer_kwargs), isHtml: true }});
            if (data.module_kwargs && Object.keys(data.module_kwargs).length > 0) {{
                optimizationItems.push({{ key: 'module_kwargs', label: 'הגדרות מודול', value: formatKwargs(data.module_kwargs), isHtml: true }});
            }}
            optimizationItems.push({{ key: 'compile_kwargs', label: 'קומפילציה', value: formatKwargs(data.compile_kwargs), isHtml: true }});

            // Data settings group
            const dataItems = [
                {{ key: 'dataset_rows', label: 'שורות', value: data.dataset_rows || '--' }},
                {{ key: 'shuffle', label: 'ערבוב', value: data.shuffle !== null ? (data.shuffle ? 'כן' : 'לא') : '--' }},
                {{ key: 'seed', label: 'Seed', value: data.seed ?? '--', mono: true }},
                {{ key: 'split_fractions', label: 'חלוקה', value: formatSplitFractions(data.split_fractions, data._split_counts), isHtml: true }},
            ];

            const groups = [
                {{ title: 'פרטי משימה', items: taskItems }},
                {{ title: 'הגדרות נתונים', items: dataItems }},
                {{ title: 'הגדרות אופטימיזציה', items: optimizationItems }},
            ];

            // Model configuration group (run jobs)
            if (jobType !== 'grid_search' && data.model_settings && typeof data.model_settings === 'object') {{
                const ms = data.model_settings;
                const modelConfigItems = [];
                if (ms.name) modelConfigItems.push({{ key: 'model_name', label: 'שם', value: ms.name, mono: true }});
                if (ms.temperature !== undefined) modelConfigItems.push({{ key: 'model_name', label: 'טמפרטורה', value: String(ms.temperature) }});
                if (ms.max_tokens) modelConfigItems.push({{ key: 'model_name', label: 'אורך מקסימלי', value: String(ms.max_tokens) }});
                if (ms.top_p !== undefined && ms.top_p !== null) modelConfigItems.push({{ key: 'model_name', label: 'Top-P', value: String(ms.top_p) }});
                if (ms.base_url) modelConfigItems.push({{ key: 'model_name', label: 'כתובת שרת', value: ms.base_url, mono: true }});
                if (ms.extra && Object.keys(ms.extra).length > 0) {{
                    modelConfigItems.push({{ key: 'model_name', label: 'נוסף', value: formatKwargs(ms.extra), isHtml: true }});
                }}
                if (modelConfigItems.length > 0) {{
                    groups.push({{ title: 'הגדרות מודל', items: modelConfigItems }});
                }}
            }}

            document.getElementById('summaryGroups').innerHTML = groups.map((group, gi) => `
                <div class="summary-group" id="group-${{gi}}">
                    <div class="summary-group-header">
                        <span>${{group.title}}</span>
                    </div>
                    <div class="summary-group-content">
                        <table class="summary-table">
                            <tbody>
                                ${{group.items.map(item => `
                                    <tr>
                                        <td>
                                            <span class="param-label"
                                                  onmouseenter="showTooltip(event, '${{escapeAttr(item.key)}}')"
                                                  onmouseleave="hideTooltip()">
                                                ${{escapeHtml(item.label)}}
                                                <span class="param-info">?</span>
                                            </span>
                                        </td>
                                        <td>${{item.isHtml ? `<span class="copyable" onclick="copyToClipboard(this.textContent.trim(), event)">${{item.value}}</span>` : `<span class="${{item.mono ? 'mono ' : ''}}copyable" onclick="copyToClipboard('${{escapeAttr(String(item.value))}}', event)">${{escapeHtml(String(item.value))}}</span>`}}</td>
                                    </tr>
                                `).join('')}}
                            </tbody>
                        </table>
                    </div>
                </div>
            `).join('');
        }}


        function detectOptimizerType(name) {{
            if (!name) return null;
            const lower = name.toLowerCase();
            if (lower.includes('mipro')) return 'mipro';
            if (lower.includes('gepa')) return 'gepa';
            return null;
        }}

        function showTooltip(event, key) {{
            const tooltip = document.getElementById('paramTooltip');
            const explanation = paramExplanations[key];
            if (!explanation) return;

            tooltip.innerHTML = `
                <div class="tooltip-title">${{explanation.title}}</div>
                <div class="tooltip-desc">${{explanation.desc}}</div>
            `;

            const rect = event.target.getBoundingClientRect();
            tooltip.style.top = `${{rect.bottom + 8}}px`;
            tooltip.style.right = `${{window.innerWidth - rect.right}}px`;
            tooltip.classList.add('visible');
        }}

        function hideTooltip() {{
            document.getElementById('paramTooltip').classList.remove('visible');
        }}

        function showKwargTooltip(event, key) {{
            const tooltip = document.getElementById('paramTooltip');
            const explanation = kwargExplanations[key];
            if (!explanation) {{
                // Show generic tooltip for unknown kwargs
                tooltip.innerHTML = `
                    <div class="tooltip-title">${{key}}</div>
                    <div class="tooltip-desc">פרמטר תצורה</div>
                `;
            }} else {{
                tooltip.innerHTML = `
                    <div class="tooltip-title">${{explanation.title}}</div>
                    <div class="tooltip-desc">${{explanation.desc}}</div>
                `;
            }}

            const rect = event.target.getBoundingClientRect();
            tooltip.style.top = `${{rect.bottom + 8}}px`;
            tooltip.style.right = `${{window.innerWidth - rect.right}}px`;
            tooltip.classList.add('visible');
        }}

        function updateComparisonCard(data, jobType) {{
            const card = document.getElementById('comparisonCard');

            let baseline = null;
            let optimized = null;

            if (jobType === 'grid_search') {{
                // For grid search, use best pair from grid_result
                const gridResult = data.grid_result;
                if (gridResult?.best_pair) {{
                    baseline = gridResult.best_pair.baseline_test_metric;
                    optimized = gridResult.best_pair.optimized_test_metric;
                }}
            }} else {{
                const result = data.result;
                if (result) {{
                    baseline = result.baseline_test_metric;
                    optimized = result.optimized_test_metric;
                }}
            }}

            if (baseline === null && optimized === null) {{
                // No data — show card with default '--' values
            }}

            document.getElementById('baselineScore').textContent =
                baseline !== null ? baseline.toFixed(2) : '--';
            document.getElementById('optimizedScore').textContent =
                optimized !== null ? optimized.toFixed(2) : '--';

            if (baseline !== null && optimized !== null && baseline > 0) {{
                const improvement = ((optimized - baseline) / baseline) * 100;
                const impEl = document.getElementById('improvement');
                impEl.textContent = `${{improvement >= 0 ? '+' : ''}}${{improvement.toFixed(1)}}%`;
                impEl.classList.toggle('negative', improvement < 0);
            }}
        }}

        function updateGridResultsPanel(gridResult, summary) {{
            const section = document.getElementById('gridResultsSection');
            const body = document.getElementById('gridResultsBody');
            const countEl = document.getElementById('gridPairsCount');

            if (!gridResult || !gridResult.pair_results || gridResult.pair_results.length === 0) {{
                body.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px; color: var(--text-secondary);">אין נתונים</td></tr>';
                countEl.textContent = '';
                return;
            }}
            const pairs = gridResult.pair_results;
            const bestIdx = gridResult.best_pair?.pair_index;

            // Model config lookups from overview (may be dicts or strings)
            const genConfigs = summary?.generation_models || [];
            const refConfigs = summary?.reflection_models || [];

            countEl.textContent = `${{gridResult.completed_pairs || 0}}/${{gridResult.total_pairs || pairs.length}} הושלמו`;

            // Sort: best first, then by optimized metric descending
            const sorted = [...pairs].sort((a, b) => {{
                if (a.pair_index === bestIdx) return -1;
                if (b.pair_index === bestIdx) return 1;
                const aScore = a.optimized_test_metric ?? -1;
                const bScore = b.optimized_test_metric ?? -1;
                return bScore - aScore;
            }});

            body.innerHTML = sorted.map(p => {{
                const isBest = p.pair_index === bestIdx;
                const isFailed = !!p.error;
                const rowClass = isBest ? 'best-pair' : (isFailed ? 'failed-pair' : '');
                const statusBadge = isBest
                    ? '<span class="pair-status-badge best">מנצח</span>'
                    : (isFailed ? '<span class="pair-status-badge failed">נכשל</span>'
                    : '<span class="pair-status-badge success">הושלם</span>');

                // Resolve model configs to show distinguishing settings
                const genConfig = findModelConfig(p.generation_model, genConfigs) || p.generation_model;
                const refConfig = findModelConfig(p.reflection_model, refConfigs) || p.reflection_model;

                return `<tr class="${{rowClass}}">
                    <td>${{p.pair_index + 1}}</td>
                    <td><span class="mono">${{escapeHtml(p.generation_model)}}</span></td>
                    <td><span class="mono">${{escapeHtml(p.reflection_model)}}</span></td>
                    <td>${{p.baseline_test_metric != null ? p.baseline_test_metric.toFixed(4) : '--'}}</td>
                    <td>${{p.optimized_test_metric != null ? p.optimized_test_metric.toFixed(4) : '--'}}</td>
                    <td>${{p.metric_improvement != null ? (p.metric_improvement >= 0 ? '+' : '') + p.metric_improvement.toFixed(4) : '--'}}</td>
                    <td>${{statusBadge}}</td>
                </tr>`;
            }}).join('');

            // Also show the prompt panel for the best pair if it has an artifact
            if (gridResult.best_pair?.program_artifact) {{
                updatePromptPanel({{ program_artifact: gridResult.best_pair.program_artifact }});
            }}
        }}

        function highlightPython(code) {{
            let html = escapeHtml(code);
            // Strings (triple-quoted first, then single/double)
            html = html.replace(/((&quot;){3}[\s\S]*?(&quot;){3}|(&quot;).*?(&quot;)|&#x27;&#x27;&#x27;[\s\S]*?&#x27;&#x27;&#x27;|&#x27;.*?&#x27;|&quot;.*?&quot;)/g, '<span class="str">$1</span>');
            // Decorators
            html = html.replace(/^(@\w+)/gm, '<span class="dec">$1</span>');
            // Comments
            html = html.replace(/(#.*$)/gm, '<span class="cmt">$1</span>');
            // Keywords
            const kws = ['import', 'from', 'class', 'def', 'return', 'if', 'else', 'elif', 'for', 'in', 'not', 'and', 'or', 'is', 'None', 'True', 'False', 'with', 'as', 'try', 'except', 'raise', 'pass', 'lambda'];
            const kwRe = new RegExp('\\\\b(' + kws.join('|') + ')\\\\b', 'g');
            html = html.replace(kwRe, '<span class="kw">$1</span>');
            // Function/method calls
            html = html.replace(/\b(\w+)(\()/g, '<span class="fn">$1</span>$2');
            return html;
        }}

        function copyCode(elementId, btn) {{
            const text = document.getElementById(elementId).textContent;
            const svgEl = btn.querySelector('svg');
            const originalSvg = svgEl.outerHTML;
            const checkSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            navigator.clipboard.writeText(text).then(() => {{
                svgEl.outerHTML = checkSvg;
                setTimeout(() => {{
                    btn.querySelector('svg').outerHTML = originalSvg;
                }}, 2000);
            }}).catch(() => alert('ההעתקה נכשלה'));
        }}

        function updateCodePanel(jobPayload) {{
            const sigSection = document.getElementById('signatureSection');
            const metSection = document.getElementById('metricSection');
            const emptyState = document.getElementById('codeEmptyState');

            const payload = jobPayload?.payload;
            if (!payload) {{
                sigSection.style.display = 'none';
                metSection.style.display = 'none';
                emptyState.style.display = '';
                return;
            }}

            const sigCode = payload.signature_code;
            const metCode = payload.metric_code;

            if (sigCode) {{
                document.getElementById('signatureCode').innerHTML = highlightPython(sigCode);
                sigSection.style.display = '';
            }} else {{
                sigSection.style.display = 'none';
            }}

            if (metCode) {{
                document.getElementById('metricCode').innerHTML = highlightPython(metCode);
                metSection.style.display = '';
            }} else {{
                metSection.style.display = 'none';
            }}

            emptyState.style.display = (sigCode || metCode) ? 'none' : '';
        }}

        function updatePromptPanel(artifact) {{
            const section = document.getElementById('promptSection');
            const emptyState = document.getElementById('promptEmptyState');

            if (!artifact?.program_artifact?.optimized_prompt) {{
                section.style.display = 'none';
                emptyState.style.display = '';
                return;
            }}

            const prompt = artifact.program_artifact.optimized_prompt;
            const content = prompt.formatted_prompt || prompt.instructions || '';
            document.getElementById('promptContent').textContent = content;
            section.style.display = '';
            emptyState.style.display = 'none';
        }}

        function copyPrompt() {{
            const content = document.getElementById('promptContent').textContent;
            const btn = document.getElementById('copyPromptBtn');
            const svgEl = btn.querySelector('svg');

            const originalSvg = svgEl.outerHTML;
            const checkSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';

            navigator.clipboard.writeText(content).then(() => {{
                svgEl.outerHTML = checkSvg;
                setTimeout(() => {{
                    btn.querySelector('svg').outerHTML = originalSvg;
                }}, 2000);
            }}).catch(() => {{
                alert('ההעתקה נכשלה');
            }});
        }}

        function updateProgressPanel(data, jobStatus) {{
            const latestMetrics = data.latest_metrics || {{}};
            const status = jobStatus || data.status;
            const isFinished = ['success', 'failed', 'cancelled'].includes(status);
            updateProgressStats(latestMetrics, isFinished, status);
        }}

        function updateProgressStats(latestMetrics, isFinished, status) {{
            const section = document.getElementById('progressSection');
            const percent = latestMetrics.tqdm_percent;

            if (isFinished) {{
                // Job is done — show 100% complete bar
                section.classList.add('done');
                document.getElementById('progressPercent').textContent = status === 'success' ? '100%' : (status === 'failed' ? 'נכשל' : 'בוטל');
                document.getElementById('progressBar').style.width = status === 'success' ? '100%' : (percent != null ? Math.min(percent, 100) + '%' : '0%');
                const n = latestMetrics.tqdm_n;
                const total = latestMetrics.tqdm_total;
                document.getElementById('progressStep').textContent =
                    (n != null && total != null) ? `${{n}} מתוך ${{total}}` : (status === 'success' ? 'הושלם' : '--');
                document.getElementById('progressRate').textContent = '--';
                document.getElementById('progressEta').textContent = '--';
                return;
            }}

            if (percent === undefined || percent === null) {{
                // No progress data yet — show waiting state
                section.classList.remove('done');
                document.getElementById('progressPercent').textContent = '--';
                document.getElementById('progressBar').style.width = '0%';
                document.getElementById('progressStep').textContent = 'ממתין לנתונים';
                document.getElementById('progressRate').textContent = '--';
                document.getElementById('progressEta').textContent = '--';
                return;
            }}

            section.classList.toggle('done', percent >= 100);

            document.getElementById('progressPercent').textContent = percent.toFixed(1) + '%';

            const bar = document.getElementById('progressBar');
            bar.style.width = Math.min(percent, 100) + '%';

            const n = latestMetrics.tqdm_n;
            const total = latestMetrics.tqdm_total;
            document.getElementById('progressStep').textContent =
                (n != null && total != null) ? `${{n}} מתוך ${{total}}` : '--';

            const rate = latestMetrics.tqdm_rate;
            if (rate != null && rate > 0) {{
                const secsPerStep = 1 / rate;
                document.getElementById('progressRate').textContent = formatDuration(secsPerStep);
            }} else {{
                document.getElementById('progressRate').textContent = '--';
            }}

            const remaining = latestMetrics.tqdm_remaining;
            document.getElementById('progressEta').textContent =
                (remaining != null) ? `~${{formatDuration(remaining)}}` : '--';
        }}

        function updateLogsPanel(logs) {{
            allLogs = logs;
            filterLogs();
        }}

        function filterLogs() {{
            const search = document.getElementById('logSearch').value.toLowerCase();
            const levelFilter = document.getElementById('logLevelFilter').value;
            const timeFilter = parseInt(document.getElementById('logTimeFilter').value) || 0;

            const now = new Date();
            let filtered = allLogs.filter(log => {{
                if (levelFilter && log.level !== levelFilter) return false;
                if (search && !log.message.toLowerCase().includes(search) && !log.logger.toLowerCase().includes(search)) return false;
                if (timeFilter > 0) {{
                    const logTime = new Date(log.timestamp);
                    if ((now - logTime) > timeFilter * 60 * 1000) return false;
                }}
                return true;
            }});

            renderLogs(filtered);
        }}

        function renderLogs(logs) {{
            const container = document.getElementById('logsTableBody');

            // Sort by timestamp (newest first)
            const sorted = [...logs].sort((a, b) =>
                new Date(b.timestamp) - new Date(a.timestamp)
            );

            // Update logs count
            document.getElementById('logsCount').textContent = `${{sorted.length}} רשומות`;

            if (sorted.length === 0) {{
                container.innerHTML = '<div class="empty-state"><div>אין פעילות להצגה</div></div>';
                return;
            }}

            container.innerHTML = sorted.map(log => `
                <div class="log-entry">
                    <span class="log-timestamp">${{formatTimestamp(log.timestamp)}}</span>
                    <span class="log-level ${{log.level}}">${{log.level}}</span>
                    <span class="log-logger">${{escapeHtml(log.logger)}}</span>
                    <span class="log-message">${{escapeHtml(log.message)}}</span>
                </div>
            `).join('');
        }}

        function showJobError(msg, title) {{
            const banner = document.getElementById('errorBanner');
            document.getElementById('errorBannerTitle').textContent = title || 'המשימה נכשלה';
            document.getElementById('errorBannerMessage').textContent = msg || 'שגיאה לא ידועה';
            banner.classList.add('show');
        }}

        function hideJobError() {{
            document.getElementById('errorBanner').classList.remove('show');
        }}

        // Helpers
        function formatSplitFractions(fractions, counts) {{
            if (!fractions) return '--';
            const trainLabel = counts ? `${{(fractions.train * 100).toFixed(0)}}% (${{counts.train}})` : `${{(fractions.train * 100).toFixed(0)}}%`;
            const valLabel = counts ? `${{(fractions.val * 100).toFixed(0)}}% (${{counts.val}})` : `${{(fractions.val * 100).toFixed(0)}}%`;
            const testLabel = counts ? `${{(fractions.test * 100).toFixed(0)}}% (${{counts.test}})` : `${{(fractions.test * 100).toFixed(0)}}%`;
            return `
                <div class="split-fractions-display">
                    <div class="split-fraction-item">
                        <span class="label">אימון:</span>
                        <span class="value">${{trainLabel}}</span>
                    </div>
                    <div class="split-fraction-item">
                        <span class="label">אימות:</span>
                        <span class="value">${{valLabel}}</span>
                    </div>
                    <div class="split-fraction-item">
                        <span class="label">בדיקה:</span>
                        <span class="value">${{testLabel}}</span>
                    </div>
                </div>
            `;
        }}

        function formatKwargs(kwargs) {{
            if (!kwargs || Object.keys(kwargs).length === 0) return '<span style="color: var(--text-disabled)">--</span>';
            return `
                <div class="kwargs-display">
                    ${{Object.entries(kwargs).map(([key, value]) => `
                        <div class="kwarg-item"
                             onmouseenter="showKwargTooltip(event, '${{escapeAttr(key)}}')"
                             onmouseleave="hideTooltip()">
                            <span class="key">${{escapeHtml(key)}}:</span>
                            <span class="value">${{escapeHtml(JSON.stringify(value))}}</span>
                        </div>
                    `).join('')}}
                </div>
            `;
        }}

        function formatTimestamp(isoString) {{
            if (!isoString) return '--';
            try {{
                return new Date(isoString).toLocaleString();
            }} catch {{
                return isoString;
            }}
        }}

        function formatTime(isoString) {{
            if (!isoString) return '--';
            try {{
                return new Date(isoString).toLocaleTimeString();
            }} catch {{
                return isoString;
            }}
        }}

        function formatDuration(seconds) {{
            if (seconds === null || seconds === undefined) return '--';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            let text;
            if (h > 0) text = `${{h}} שעות ${{m}} דק׳ ${{s}} שנ׳`;
            else if (m > 0) text = `${{m}} דק׳ ${{s}} שנ׳`;
            else text = `${{s}} שנ׳`;
            return '\u2066' + text + '\u2069';
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function escapeAttr(text) {{
            return String(text)
                .replace(/&/g, '&amp;')
                .replace(/'/g, '&#39;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }}

        function copyToClipboard(text, event) {{
            navigator.clipboard.writeText(text).then(() => {{
                const feedback = document.getElementById('copyFeedback');
                const target = event.target;
                const rect = target.getBoundingClientRect();

                // Position centered above the element
                feedback.style.top = `${{rect.top - 45}}px`;
                feedback.style.left = `${{rect.left + (rect.width / 2)}}px`;
                feedback.style.right = 'auto';

                feedback.classList.add('show');
                setTimeout(() => feedback.classList.remove('show'), 1000);
            }}).catch(() => {{
                alert('ההעתקה נכשלה');
            }});
        }}

    </script>
</body>
</html>'''


def get_dashboard_dataframe(
    job_id: str,
    api_base_url: str = DEFAULT_API_BASE_URL
) -> pd.DataFrame:
    """Return the dashboard HTML as a DataFrame with a single cell.

    Args:
        job_id: Job identifier. Data will be fetched and injected.
        api_base_url: Base URL of the API server.

    Returns:
        pd.DataFrame: DataFrame with one column 'html' and one row containing the HTML.
    """
    html = generate_dashboard_html(job_id, api_base_url)
    return pd.DataFrame({'html': [html]})
