/**
 * Hospitality Analytics - FINAL v14
 * 
 * Modernized UI, Card-based theme compatible with Frappe Desk light/dark modes,
 * Auto-load on page visit (Default MTD), Quick Date Filter Chips,
 * and robust Clone & Replace rendering.
 */

frappe.provide('frappe.hospitality');

function get_chart_colors(count) {
    const base = ['#6366f1', '#a855f7', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#06b6d4'];
    if (count <= base.length) return base;
    const colors = base.slice();
    for (let i = base.length; i < count; i++) {
        const hue = Math.round((360 * i) / count);
        colors.push(`hsl(${hue}, 65%, 55%)`);
    }
    return colors;
}

frappe.hospitality.FinalAnalyticsV13 = class {
    constructor() {
        this.fromDate = null;
        this.toDate = null;
        this.charts = [
            { id: 'chart-occ', name: 'Occupancy Rate Trend', title: __('Tỷ Lệ Lấp Đầy Phòng (Occupancy)'), type: 'line' },
            { id: 'chart-adr', name: 'Average Daily Rate (ADR)', title: __('Giá Phòng Bình Quân Ngày (ADR)'), type: 'line' },
            { id: 'chart-revpar', name: 'RevPAR Trend', title: __('Doanh Thu Phòng Khả Dụng (RevPAR)'), type: 'line' },
            { id: 'chart-guest', name: 'Guest Type Distribution', title: __('Cơ Cấu Nguồn Khách'), type: 'pie' },
            { id: 'chart-revext', name: 'Revenue vs Expense Trend', title: __('Doanh Thu & Chi Phí'), type: 'line' },
            { id: 'chart-gp', name: 'Gross Profit Margin Trend', title: __('Tỷ Suất Lợi Nhuận Gộp'), type: 'line' },
            { id: 'chart-exp', name: 'Expense Breakdown', title: __('Cơ Cấu Khoản Mục Chi Phí'), type: 'donut' },
            { id: 'chart-reception', name: 'Sales by Reception', title: __('Doanh Số Theo Nhân Viên Lễ Tân'), type: 'bar' },
            { id: 'chart-payment', name: 'Payment Mode Distribution', title: __('Cơ Cấu Phương Thức Thanh Toán'), type: 'donut' },
            { id: 'chart-maintenance', name: 'Maintenance Cost by Room Type', title: __('Chi Phí Bảo Trì Theo Loại Phòng'), type: 'bar' }
        ];
        this.setup_observer();
        this.init();
    }

    get_date_range(type) {
        const formatDate = (d) => {
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        };

        const now = new Date();
        const to = formatDate(now);

        if (type === 'today') {
            return { from: to, to: to };
        } else if (type === '7days') {
            const d = new Date();
            d.setDate(d.getDate() - 6);
            return { from: formatDate(d), to: to };
        } else if (type === 'mtd') {
            const first = new Date(now.getFullYear(), now.getMonth(), 1);
            return { from: formatDate(first), to: to };
        } else if (type === 'last_month') {
            const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            const last = new Date(now.getFullYear(), now.getMonth(), 0);
            return { from: formatDate(first), to: formatDate(last) };
        } else if (type === 'ytd') {
            const first = new Date(now.getFullYear(), 0, 1);
            return { from: formatDate(first), to: to };
        }
        return { from: to, to: to };
    }

    init() {
        if (!this.is_analytics_page()) return;
        const defaults = this.get_date_range('mtd');
        this.fromDate = defaults.from;
        this.toDate = defaults.to;
        this.inject_ui();
        this.fetch_and_draw();
    }

    is_analytics_page() {
        const url = window.location.href;
        const page_name = frappe.container?.page?.page?.name || "";
        return url.includes('hospitality-analytics') || url.includes('hospitality_analytics') || page_name.includes('hospitality_analytics');
    }

    setup_observer() {
        this.observer = new MutationObserver(() => {
            if (this.is_analytics_page() && !$('#hos-v13-controls-inner').length) {
                this.inject_ui();
                this.fetch_and_draw();
            }
        });
        this.observer.observe(document.body, { childList: true, subtree: true });
    }

    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
    }

    inject_ui() {
        const $target = $('#hos-v10-controls, [id*="AN_FINAL"]');
        if (!$target.length) return;

        $target.empty().append('<div id="hos-v13-controls-inner"></div>');
        const $inner = $('#hos-v13-controls-inner');

        $inner.html(`
            <div class="analytics-filter-card" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 12px; padding: 18px 20px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px;">
                    <div style="font-weight: 700; font-size: 15px; color: var(--text-color, #111827); display: flex; align-items: center; gap: 8px;">
                        <i class="fa fa-sliders text-primary"></i> ${__('Bộ Lọc Phân Tích Dữ Liệu Khách Sạn')}
                    </div>
                    <div class="quick-date-chips" style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <button class="btn btn-xs btn-default date-chip" data-range="today" style="border-radius: 14px; font-weight: 600;">${__('Hôm nay')}</button>
                        <button class="btn btn-xs btn-default date-chip" data-range="7days" style="border-radius: 14px; font-weight: 600;">${__('7 ngày')}</button>
                        <button class="btn btn-xs btn-primary date-chip active" data-range="mtd" style="border-radius: 14px; font-weight: 600;">${__('Tháng này (MTD)')}</button>
                        <button class="btn btn-xs btn-default date-chip" data-range="last_month" style="border-radius: 14px; font-weight: 600;">${__('Tháng trước')}</button>
                        <button class="btn btn-xs btn-default date-chip" data-range="ytd" style="border-radius: 14px; font-weight: 600;">${__('Năm nay (YTD)')}</button>
                    </div>
                </div>
                <div class="row" style="align-items: flex-end;">
                    <div class="col-sm-4 col-xs-12" style="margin-bottom: 8px;">
                        <label style="color: var(--text-muted, #6b7280); font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px;">${__('Từ ngày')}</label>
                        <input type="date" id="v13-from-date" class="form-control" value="${this.fromDate || ''}" style="border-radius: 8px; font-weight: 600; border: 1px solid var(--border-color, #d1d5db); background: var(--control-bg, #ffffff); color: var(--text-color, #111827);">
                    </div>
                    <div class="col-sm-4 col-xs-12" style="margin-bottom: 8px;">
                        <label style="color: var(--text-muted, #6b7280); font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px;">${__('Đến ngày')}</label>
                        <input type="date" id="v13-to-date" class="form-control" value="${this.toDate || ''}" style="border-radius: 8px; font-weight: 600; border: 1px solid var(--border-color, #d1d5db); background: var(--control-bg, #ffffff); color: var(--text-color, #111827);">
                    </div>
                    <div class="col-sm-4 col-xs-12" style="margin-bottom: 8px;">
                        <button id="v13-draw-btn" class="btn btn-primary btn-block" style="font-weight: 700; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; gap: 6px;">
                            <i class="fa fa-refresh"></i> ${__('TẢI LẠI BIỂU ĐỒ')}
                        </button>
                    </div>
                </div>
                <div id="v13-guide" style="margin-top: 10px; color: var(--text-muted, #6b7280); font-size: 12px; text-align: center;">
                    <i class="fa fa-info-circle text-info"></i> ${__('Đang hiển thị dữ liệu từ {0} đến {1}', [this.fromDate, this.toDate])}
                </div>
            </div>
        `);

        // Quick range chips binding
        $inner.find('.date-chip').on('click', (e) => {
            const range = $(e.currentTarget).data('range');
            $inner.find('.date-chip').removeClass('btn-primary active').addClass('btn-default');
            $(e.currentTarget).removeClass('btn-default').addClass('btn-primary active');

            const dates = this.get_date_range(range);
            this.fromDate = dates.from;
            this.toDate = dates.to;
            $('#v13-from-date').val(this.fromDate);
            $('#v13-to-date').val(this.toDate);
            this.fetch_and_draw();
        });

        $('#v13-from-date, #v13-to-date').on('change', () => {
            this.fromDate = $('#v13-from-date').val();
            this.toDate = $('#v13-to-date').val();
            $inner.find('.date-chip').removeClass('btn-primary active').addClass('btn-default');
            if (this.fromDate && this.toDate) {
                this.fetch_and_draw();
            }
        });

        $('#v13-draw-btn').on('click', () => {
            this.fromDate = $('#v13-from-date').val();
            this.toDate = $('#v13-to-date').val();
            if (!this.fromDate || !this.toDate) {
                frappe.msgprint(__('Vui lòng chọn đầy đủ cả Từ ngày và Đến ngày.'));
                return;
            }
            this.fetch_and_draw();
        });
    }

    fetch_and_draw() {
        if (!this.fromDate || !this.toDate) return;
        $('#v13-guide').html(`<span style="color: #2563eb; font-weight: 600;"><i class="fa fa-spinner fa-spin"></i> ${__('Đang đồng bộ dữ liệu biểu đồ…')}</span>`);

        let pending = this.charts.length;
        const onFinish = () => {
            pending--;
            if (pending <= 0) {
                $('#v13-guide').html(`<span style="color: #059669; font-weight: 600;"><i class="fa fa-check-circle"></i> ${__('Đã đồng bộ dữ liệu từ {0} đến {1}', [this.fromDate, this.toDate])}</span>`);
            }
        };

        this.charts.forEach(chart => {
            let el = document.getElementById(chart.id);
            if (!el || !el.parentNode) {
                onFinish();
                return;
            }

            // CLONE & REPLACE Strategy to sever stale observers
            const newEl = el.cloneNode(false);
            el.parentNode.replaceChild(newEl, el);
            el = newEl;

            el.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; height: 250px; color: var(--text-muted, #9ca3af); font-size: 13px;"><i class="fa fa-spinner fa-spin fa-fw" style="margin-right: 6px;"></i> ${__('Đang tải…')}</div>`;

            frappe.call({
                method: 'hospitality_core.hospitality_core.dashboard_data.get_hospitality_analytics_data',
                args: {
                    chart_name: chart.name,
                    from_date: this.fromDate,
                    to_date: this.toDate
                },
                callback: (r) => {
                    const data = r.message;
                    el.innerHTML = '';
                    if (!data || !data.labels || data.labels.length === 0) {
                        el.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; height: 250px; color: var(--text-muted, #9ca3af); font-size: 13px;"><i class="fa fa-info-circle" style="margin-right: 6px;"></i> ${__('Chưa có dữ liệu')}</div>`;
                        onFinish();
                        return;
                    }

                    try {
                        const isCircle = chart.type === 'pie' || chart.type === 'donut';
                        const chartConfig = {
                            title: chart.title || chart.name,
                            data: data,
                            type: chart.type,
                            height: 250,
                            colors: get_chart_colors(data.labels.length)
                        };

                        if (!isCircle) {
                            chartConfig.axisOptions = { xIsSeries: true, shortenYAxisNumbers: 1 };
                        }

                        new frappe.Chart(el, chartConfig);
                    } catch (err) {
                        console.error(`[v14] Render Error on ${chart.name}:`, err);
                    }
                    onFinish();
                },
                error: () => {
                    el.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; height: 250px; color: #ef4444; font-size: 13px;"><i class="fa fa-exclamation-triangle" style="margin-right: 6px;"></i> ${__('Lỗi tải dữ liệu')}</div>`;
                    onFinish();
                }
            });
        });
    }
};

// Global Boot
$(document).on('page-change', () => {
    setTimeout(() => {
        if (window.hospitality_v13_manager) {
            window.hospitality_v13_manager.destroy();
        }
        window.hospitality_v13_manager = new frappe.hospitality.FinalAnalyticsV13();
    }, 1000);
});

$(() => {
    if (!window.hospitality_v13_manager) {
        window.hospitality_v13_manager = new frappe.hospitality.FinalAnalyticsV13();
    }
});
