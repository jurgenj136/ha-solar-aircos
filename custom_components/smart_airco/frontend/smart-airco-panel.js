class SmartAircoPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._narrow = false;
    this._activeEntryId = null;
    this._notice = null;
    this._renderSignature = null;
    this._refreshTimerIds = [];
  }

  set hass(hass) {
    const nextSignature = this._computeRenderSignature(hass);
    this._hass = hass;
    if (nextSignature === this._renderSignature) {
      return;
    }
    this._renderSignature = nextSignature;
    this._render();
  }

  set narrow(value) {
    this._narrow = Boolean(value);
    this._render();
  }

  disconnectedCallback() {
    this._clearRefreshTimers();
  }

  _getStates() {
    return Object.values(this._hass?.states || {});
  }

  _computeRenderSignature(hass) {
    const states = Object.values(hass?.states || {});
    const controllers = states
      .filter(
        (state) =>
          state.entity_id.startsWith('climate.') &&
          state.attributes?.smart_airco_controller === true
      )
      .map((state) => ({
        entity_id: state.entity_id,
        state: state.state,
        attributes: state.attributes,
      }));
    const climateOptions = states
      .filter((state) => state.entity_id.startsWith('climate.'))
      .map((state) => state.entity_id)
      .sort();
    const sensorOptions = states
      .filter((state) => state.entity_id.startsWith('sensor.'))
      .map((state) => ({
        entity_id: state.entity_id,
        device_class: state.attributes?.device_class || null,
        unit: state.attributes?.unit_of_measurement || null,
      }))
      .sort((left, right) => left.entity_id.localeCompare(right.entity_id));
    const windowOptions = states
      .filter(
        (state) =>
          state.entity_id.startsWith('binary_sensor.') &&
          ['door', 'window', 'opening'].includes(state.attributes?.device_class || '')
      )
      .map((state) => state.entity_id)
      .sort();

    return JSON.stringify({
      controllers,
      climateOptions,
      sensorOptions,
      windowOptions,
    });
  }

  _getControllers(states) {
    return states.filter(
      (state) =>
        state.entity_id.startsWith('climate.') &&
        state.attributes?.smart_airco_controller === true
    );
  }

  _getControllerSelection(controllers) {
    if (
      !this._activeEntryId ||
      !controllers.some(
        (controller) => controller.attributes?.smart_airco_entry_id === this._activeEntryId
      )
    ) {
      this._activeEntryId = controllers[0]?.attributes?.smart_airco_entry_id || null;
    }

    const controller =
      controllers.find(
        (candidate) => candidate.attributes?.smart_airco_entry_id === this._activeEntryId
      ) || controllers[0] || null;

    this._activeEntryId = controller?.attributes?.smart_airco_entry_id || null;
    return controller;
  }

  _escape(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  _selectOptions(items, selected = '', emptyLabel = '(none)') {
    return ['']
      .concat(items)
      .map((value) => {
        const isSelected = value === selected ? 'selected' : '';
        const label = value || emptyLabel;
        return `<option value="${this._escape(value)}" ${isSelected}>${this._escape(label)}</option>`;
      })
      .join('');
  }

  _multiSelectOptions(items, selected = []) {
    return items
      .map((value) => {
        const isSelected = selected.includes(value) ? 'selected' : '';
        return `<option value="${this._escape(value)}" ${isSelected}>${this._escape(value)}</option>`;
      })
      .join('');
  }

  _showNotice(message, tone = 'info') {
    this._notice = { message, tone };
    this._render();
  }

  _clearNotice() {
    this._notice = null;
  }

  _clearRefreshTimers() {
    this._refreshTimerIds.forEach((timerId) => {
      window.clearTimeout(timerId);
    });
    this._refreshTimerIds = [];
  }

  _scheduleFollowUpRenders() {
    this._clearRefreshTimers();
    [300, 900, 1800].forEach((delay) => {
      const timerId = window.setTimeout(() => this._render(), delay);
      this._refreshTimerIds.push(timerId);
    });
  }

  async _callSmartAircoService(service, data = {}) {
    if (!this._hass) {
      throw new Error('Home Assistant connection not available');
    }

    const payload = this._activeEntryId
      ? { config_entry_id: this._activeEntryId, ...data }
      : data;

    await this._hass.callService('smart_airco', service, payload);
    this._scheduleFollowUpRenders();
  }

  async _runPanelAction(action, successMessage) {
    try {
      this._clearNotice();
      await action();
      this._showNotice(successMessage, 'success');
    } catch (error) {
      console.error(error);
      this._showNotice(error?.message || 'Action failed.', 'error');
    }
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }

    const states = this._getStates();
    const controllers = this._getControllers(states);
    const controller = controllers.length ? this._getControllerSelection(controllers) : null;
    const attrs = controller?.attributes || {};
    const managedClimates = Array.isArray(attrs.managed_climates) ? attrs.managed_climates : [];
    const configuredClimates = attrs.configured_climate_entity_ids || [];

    const powerOptions = states
      .filter(
        (state) =>
          state.entity_id.startsWith('sensor.') &&
          (state.attributes?.device_class === 'power' ||
            String(state.attributes?.unit_of_measurement || '')
              .toLowerCase()
              .includes('w'))
      )
      .map((state) => state.entity_id)
      .sort();

    const sensorOptions = states
      .filter((state) => state.entity_id.startsWith('sensor.'))
      .map((state) => state.entity_id)
      .sort();

    const windowOptions = states
      .filter(
        (state) =>
          state.entity_id.startsWith('binary_sensor.') &&
          ['door', 'window', 'opening'].includes(state.attributes?.device_class || '')
      )
      .map((state) => state.entity_id)
      .sort();

    const climateOptions = states
      .filter((state) => state.entity_id.startsWith('climate.'))
      .map((state) => state.entity_id)
      .sort();

    const availableClimateOptions = climateOptions.filter(
      (entityId) => !configuredClimates.includes(entityId) && entityId !== controller?.entity_id
    );

    const criticalErrors = Array.isArray(attrs.critical_input_errors)
      ? attrs.critical_input_errors
      : [];

    const noticeHtml = this._notice
      ? `<div class="notice show ${this._escape(this._notice.tone)}">${this._escape(
          this._notice.message
        )}</div>`
      : '<div class="notice"></div>';

    const instancePickerHtml =
      controllers.length > 1
        ? `
          <section class="card">
            <div class="row compact">
              <label>Controller instance</label>
              <select id="sel-controller">
                ${controllers
                  .map((candidate) => {
                    const entryId = candidate.attributes?.smart_airco_entry_id || '';
                    const title = candidate.attributes?.friendly_name || candidate.entity_id;
                    const selected = entryId === this._activeEntryId ? 'selected' : '';
                    return `<option value="${this._escape(entryId)}" ${selected}>${this._escape(
                      title
                    )}</option>`;
                  })
                  .join('')}
              </select>
            </div>
          </section>
        `
        : '';

    const overviewHtml = controller
      ? `
        <div class="grid">
          <div class="metric"><span class="label">Status</span><strong>${this._escape(
            attrs.decision_reason || 'unknown'
          )}</strong></div>
          <div class="metric"><span class="label">Predicted surplus</span><strong>${this._escape(
            attrs.predicted_surplus || 0
          )} W</strong></div>
          <div class="metric"><span class="label">Current surplus</span><strong>${this._escape(
            attrs.current_surplus || 0
          )} W</strong></div>
          <div class="metric"><span class="label">Running ACs</span><strong>${this._escape(
            attrs.running_entities || 0
          )}</strong></div>
          <div class="metric"><span class="label">Manual overrides</span><strong>${this._escape(
            attrs.manual_override_entities || 0
          )}</strong></div>
          <div class="metric"><span class="label">Critical inputs valid</span><strong>${
            attrs.critical_inputs_valid ? 'yes' : 'no'
          }</strong></div>
        </div>
        ${
          criticalErrors.length
            ? `<div class="callout error"><strong>Critical input errors:</strong> ${this._escape(
                criticalErrors.join(', ')
              )}</div>`
            : ''
        }
      `
      : '<div class="empty">Smart Airco controller not found yet. Add the integration first.</div>';

    const climateRowsHtml = managedClimates.length
      ? managedClimates
          .map((climate, index) => {
            const powerOptionsHtml = this._selectOptions(
              powerOptions,
              climate.power_sensor || ''
            );
            const windowOptionsHtml = this._multiSelectOptions(
              windowOptions,
              climate.window_sensors || []
            );
            return `
              <tr data-row-index="${index}">
                <td>${this._escape(climate.name || climate.entity_id)}</td>
                <td><code>${this._escape(climate.entity_id)}</code></td>
                <td><input data-field="priority" type="number" min="1" max="10" value="${this._escape(
                  climate.priority
                )}" /></td>
                <td><input data-field="enabled" type="checkbox" ${
                  climate.enabled ? 'checked' : ''
                } /></td>
                <td>
                  <div class="stack">
                    <span>${this._escape(climate.windows_open)}</span>
                    <details>
                      <summary>Edit</summary>
                      <label>Window sensors</label>
                      <select data-field="window_sensors" multiple>
                        ${windowOptionsHtml}
                      </select>
                      <button data-action="save-windows" type="button">Save</button>
                    </details>
                  </div>
                </td>
                <td>
                  <div class="stack">
                    <span>${this._escape(climate.power)} W</span>
                    <details>
                      <summary>Edit</summary>
                      <label><input data-field="use_estimated_power" type="checkbox" ${
                        climate.use_estimated_power ? 'checked' : ''
                      } /> Use estimated power</label>
                      <label>Estimated W</label>
                      <input data-field="wattage" type="number" min="100" max="5000" value="${this._escape(
                        climate.estimated_wattage
                      )}" />
                      <label>Power sensor</label>
                      <select data-field="power_sensor">${powerOptionsHtml}</select>
                      <button data-action="save-power" type="button">Save</button>
                    </details>
                  </div>
                </td>
                <td>
                  <div class="stack">
                    ${climate.manual_override ? '<span class="tag warn">Manual override</span>' : ''}
                    <span class="muted">${this._escape(climate.reason || 'unknown')}</span>
                  </div>
                </td>
                <td>
                  <div class="stack actions">
                    <button data-action="save-priority" type="button">Save priority</button>
                    <button data-action="remove-climate" type="button">Remove</button>
                  </div>
                </td>
              </tr>
            `;
          })
          .join('')
      : '<tr><td colspan="8" class="empty">No managed climates configured yet.</td></tr>';

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          min-height: 100vh;
        }
        * { box-sizing: border-box; }
        .wrap {
          max-width: 1100px;
          margin: 0 auto;
          padding: 24px;
          font-family: var(--primary-font-family, system-ui, sans-serif);
        }
        .hero {
          margin-bottom: 20px;
          padding: 20px 24px;
          border-radius: 18px;
          background: linear-gradient(135deg, rgba(14, 116, 144, 0.18), rgba(2, 132, 199, 0.12));
          border: 1px solid rgba(125, 211, 252, 0.18);
        }
        h1 {
          margin: 0 0 8px;
          font-size: 1.8rem;
        }
        .subtitle {
          opacity: 0.78;
          margin: 0;
        }
        .card {
          margin-bottom: 16px;
          padding: 18px;
          border-radius: 16px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          background: var(--card-background-color, rgba(255, 255, 255, 0.04));
        }
        .card h2 {
          margin: 0 0 14px;
          font-size: 1.05rem;
        }
        .row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 12px;
          align-items: end;
        }
        .row.compact {
          grid-template-columns: 160px minmax(260px, 420px);
          align-items: center;
        }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px;
        }
        .metric {
          padding: 12px 14px;
          border-radius: 12px;
          background: rgba(148, 163, 184, 0.08);
        }
        .label {
          display: block;
          margin-bottom: 6px;
          font-size: 0.82rem;
          opacity: 0.78;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        label {
          display: block;
          margin-bottom: 6px;
          font-size: 0.9rem;
        }
        input,
        select,
        button,
        textarea {
          width: 100%;
          font: inherit;
          color: inherit;
        }
        input,
        select {
          padding: 10px 12px;
          border-radius: 10px;
          border: 1px solid rgba(148, 163, 184, 0.28);
          background: rgba(15, 23, 42, 0.08);
        }
        input[type='checkbox'] {
          width: auto;
          margin-right: 6px;
        }
        select[multiple] {
          min-height: 100px;
        }
        button {
          padding: 10px 14px;
          border-radius: 10px;
          border: 1px solid rgba(14, 165, 233, 0.24);
          background: rgba(14, 165, 233, 0.14);
          cursor: pointer;
        }
        button:hover {
          background: rgba(14, 165, 233, 0.22);
        }
        .button-row {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          margin-top: 14px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
        }
        th,
        td {
          padding: 10px 8px;
          border-bottom: 1px solid rgba(148, 163, 184, 0.14);
          text-align: left;
          vertical-align: top;
        }
        th {
          font-size: 0.84rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          opacity: 0.72;
        }
        .stack {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .actions button {
          width: 100%;
        }
        .tag {
          display: inline-flex;
          align-items: center;
          width: fit-content;
          padding: 4px 10px;
          border-radius: 999px;
          border: 1px solid rgba(148, 163, 184, 0.2);
          font-size: 0.82rem;
        }
        .tag.warn {
          background: rgba(217, 119, 6, 0.16);
          border-color: rgba(217, 119, 6, 0.28);
        }
        .notice {
          display: none;
          margin-bottom: 16px;
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .notice.show { display: block; }
        .notice.info { background: rgba(59, 130, 246, 0.12); }
        .notice.success { background: rgba(22, 163, 74, 0.12); }
        .notice.error { background: rgba(220, 38, 38, 0.14); }
        .callout {
          margin-top: 14px;
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .callout.error {
          background: rgba(220, 38, 38, 0.12);
        }
        .muted {
          opacity: 0.76;
        }
        .empty {
          opacity: 0.78;
        }
        code {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.88rem;
        }
        @media (max-width: 900px) {
          .wrap { padding: 16px; }
          .row.compact { grid-template-columns: 1fr; }
          table, thead, tbody, th, td, tr { display: block; }
          thead { display: none; }
          tr {
            margin-bottom: 14px;
            padding: 12px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 12px;
          }
          td {
            border: 0;
            padding: 6px 0;
          }
        }
      </style>
      <div class="wrap">
        <section class="hero">
          <h1>Smart Airco</h1>
          <p class="subtitle">Solar-aware orchestration for your managed climate entities.</p>
        </section>
        ${noticeHtml}
        ${instancePickerHtml}
        <section class="card">
          <h2>Global settings</h2>
          <div class="row">
            <div>
              <label for="sel-forecast">Forecast sensor</label>
              <select id="sel-forecast">${this._selectOptions(
                sensorOptions,
                attrs.forecast_sensor || ''
              )}</select>
            </div>
            <div>
              <label for="sel-production">Production sensor</label>
              <select id="sel-production">${this._selectOptions(
                sensorOptions,
                attrs.production_sensor || ''
              )}</select>
            </div>
            <div>
              <label for="sel-netexport">Net export sensor</label>
              <select id="sel-netexport">${this._selectOptions(
                sensorOptions,
                attrs.net_export_sensor || ''
              )}</select>
            </div>
            <div>
              <label for="inp-interval">Update interval (minutes)</label>
              <input id="inp-interval" type="number" min="1" max="60" value="${this._escape(
                attrs.update_interval_minutes ?? 5
              )}" />
            </div>
          </div>
          <div class="button-row">
            <button id="btn-save-global" type="button" ${controller ? '' : 'disabled'}>Save global settings</button>
            <button id="btn-evaluate" type="button" ${controller ? '' : 'disabled'}>Evaluate conditions</button>
            <button id="btn-execute" type="button" ${controller ? '' : 'disabled'}>Execute decisions</button>
          </div>
        </section>
        <section class="card">
          <h2>Overview</h2>
          ${overviewHtml}
        </section>
        <section class="card">
          <h2>Add managed climate</h2>
          <div class="row">
            <div>
              <label for="add-entity">Climate entity</label>
              <select id="add-entity">${this._selectOptions(
                availableClimateOptions,
                '',
                availableClimateOptions.length ? '(select climate)' : '(all climates already added)'
              )}</select>
            </div>
            <div>
              <label for="add-name">Display name</label>
              <input id="add-name" type="text" placeholder="Living Room" />
            </div>
            <div>
              <label for="add-priority">Priority</label>
              <input id="add-priority" type="number" min="1" max="10" value="1" />
            </div>
            <div>
              <label><input id="add-enabled" type="checkbox" checked /> Enabled</label>
            </div>
          </div>
          <div class="row">
            <div>
              <label><input id="add-use-estimated" type="checkbox" checked /> Use estimated power</label>
            </div>
            <div>
              <label for="add-wattage">Estimated wattage</label>
              <input id="add-wattage" type="number" min="100" max="5000" value="1000" />
            </div>
            <div>
              <label for="add-power-sensor">Power sensor</label>
              <select id="add-power-sensor">${this._selectOptions(powerOptions)}</select>
            </div>
          </div>
          <div class="button-row">
            <button id="btn-add-climate" type="button" ${controller ? '' : 'disabled'}>Add climate</button>
          </div>
        </section>
        <section class="card">
          <h2>Managed climates</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Entity</th>
                <th>Priority</th>
                <th>Enabled</th>
                <th>Windows</th>
                <th>Power</th>
                <th>Decision</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${climateRowsHtml}</tbody>
          </table>
        </section>
      </div>
    `;

    this._attachListeners(managedClimates);
  }

  _attachListeners(managedClimates) {
    const root = this.shadowRoot;
    if (!root) {
      return;
    }

    const controllerSelect = root.getElementById('sel-controller');
    controllerSelect?.addEventListener('change', (event) => {
      this._activeEntryId = event.target.value || null;
      this._clearNotice();
      this._render();
    });

    root.getElementById('btn-evaluate')?.addEventListener('click', async () => {
      await this._runPanelAction(async () => {
        await this._callSmartAircoService('evaluate_conditions');
      }, 'Condition evaluation requested.');
    });

    root.getElementById('btn-execute')?.addEventListener('click', async () => {
      await this._runPanelAction(async () => {
        await this._callSmartAircoService('execute_decisions');
      }, 'Decision execution requested.');
    });

    root.getElementById('btn-save-global')?.addEventListener('click', async () => {
      await this._runPanelAction(async () => {
        const forecastSensor = root.getElementById('sel-forecast')?.value?.trim() || null;
        const productionSensor = root.getElementById('sel-production')?.value?.trim() || null;
        const netExportSensor = root.getElementById('sel-netexport')?.value?.trim() || null;
        const updateIntervalMinutes = Number.parseInt(
          root.getElementById('inp-interval')?.value || '5',
          10
        );
        await this._callSmartAircoService('set_global_settings', {
          forecast_sensor: forecastSensor,
          production_sensor: productionSensor,
          net_export_sensor: netExportSensor,
          update_interval_minutes: Number.isFinite(updateIntervalMinutes)
            ? updateIntervalMinutes
            : 5,
        });
      }, 'Global settings updated.');
    });

    root.getElementById('btn-add-climate')?.addEventListener('click', async () => {
      const entityId = root.getElementById('add-entity')?.value?.trim() || '';
      if (!entityId) {
        this._showNotice('Select a climate entity before adding it.', 'error');
        return;
      }
      await this._runPanelAction(async () => {
        const name = root.getElementById('add-name')?.value?.trim() || '';
        const priority = Number.parseInt(
          root.getElementById('add-priority')?.value || '1',
          10
        );
        const enabled = Boolean(root.getElementById('add-enabled')?.checked);
        const useEstimatedPower = Boolean(root.getElementById('add-use-estimated')?.checked);
        const wattage = Number.parseInt(
          root.getElementById('add-wattage')?.value || '1000',
          10
        );
        const powerSensor = root.getElementById('add-power-sensor')?.value?.trim() || null;
        const payload = {
          entity_id: entityId,
          priority: Number.isFinite(priority) ? priority : 1,
          enabled,
          use_estimated_power: useEstimatedPower,
          wattage: Number.isFinite(wattage) ? wattage : 1000,
        };
        if (name) {
          payload.name = name;
        }
        if (powerSensor) {
          payload.power_sensor = powerSensor;
        }
        await this._callSmartAircoService('add_climate', payload);
      }, 'Climate added.');
    });

    root.querySelectorAll('tr[data-row-index]').forEach((row) => {
      const index = Number.parseInt(row.getAttribute('data-row-index') || '-1', 10);
      const climate = managedClimates[index];
      if (!climate) {
        return;
      }

      row.querySelector('[data-field="enabled"]')?.addEventListener('change', async (event) => {
        await this._runPanelAction(async () => {
          await this._callSmartAircoService('toggle_climate_entity', {
            entity_id: climate.entity_id,
            enabled: Boolean(event.target.checked),
          });
        }, event.target.checked ? 'Automation re-enabled for this AC.' : 'Automation disabled for this AC.');
      });

      row.querySelector('[data-action="save-priority"]')?.addEventListener('click', async () => {
        const priority = Number.parseInt(
          row.querySelector('[data-field="priority"]')?.value || String(climate.priority || 1),
          10
        );
        if (!Number.isFinite(priority)) {
          this._showNotice('Priority must be a number.', 'error');
          return;
        }
        await this._runPanelAction(async () => {
          await this._callSmartAircoService('set_climate_priority', {
            entity_id: climate.entity_id,
            priority,
          });
        }, 'Priority updated.');
      });

      row.querySelector('[data-action="save-power"]')?.addEventListener('click', async () => {
        const wattage = Number.parseInt(
          row.querySelector('[data-field="wattage"]')?.value || String(climate.estimated_wattage || 1000),
          10
        );
        await this._runPanelAction(async () => {
          await this._callSmartAircoService('set_climate_power', {
            entity_id: climate.entity_id,
            use_estimated_power: Boolean(
              row.querySelector('[data-field="use_estimated_power"]')?.checked
            ),
            wattage: Number.isFinite(wattage) ? wattage : 1000,
            power_sensor:
              row.querySelector('[data-field="power_sensor"]')?.value?.trim() || null,
          });
        }, 'Power settings updated.');
      });

      row.querySelector('[data-action="save-windows"]')?.addEventListener('click', async () => {
        const selected = Array.from(
          row.querySelector('[data-field="window_sensors"]')?.selectedOptions || []
        ).map((option) => option.value);
        await this._runPanelAction(async () => {
          await this._callSmartAircoService('set_climate_windows', {
            entity_id: climate.entity_id,
            window_sensors: selected,
          });
        }, 'Window sensor settings updated.');
      });

      row.querySelector('[data-action="remove-climate"]')?.addEventListener('click', async () => {
        await this._runPanelAction(async () => {
          await this._callSmartAircoService('remove_climate', {
            entity_id: climate.entity_id,
          });
        }, 'Climate removed.');
      });
    });
  }
}

if (!customElements.get('smart-airco-panel')) {
  customElements.define('smart-airco-panel', SmartAircoPanel);
}
