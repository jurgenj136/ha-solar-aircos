class SmartAircoPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._narrow = false;
    this._activeEntryId = null;
    this._activeEntryTitle = null;
    this._notice = null;
    this._renderSignature = null;
    this._globalDraft = null;
    this._addDraft = null;
    this._climateDrafts = {};
    this._editingClimateId = null;
    this._pendingActions = new Set();
    this._refreshTimerIds = [];

    this.shadowRoot.addEventListener('click', (event) => this._handleClick(event));
    this.shadowRoot.addEventListener('input', (event) => this._handleInput(event));
    this.shadowRoot.addEventListener('change', (event) => this._handleChange(event));
  }

  set hass(hass) {
    const nextSignature = this._computeRenderSignature(hass);
    this._hass = hass;
    this._syncViewState();
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
    const sensors = states
      .filter((state) => state.entity_id.startsWith('sensor.'))
      .map((state) => ({
        entity_id: state.entity_id,
        device_class: state.attributes?.device_class || null,
        unit: state.attributes?.unit_of_measurement || null,
      }))
      .sort((left, right) => left.entity_id.localeCompare(right.entity_id));
    const climates = states
      .filter((state) => state.entity_id.startsWith('climate.'))
      .map((state) => state.entity_id)
      .sort();
    const windows = states
      .filter(
        (state) =>
          state.entity_id.startsWith('binary_sensor.') &&
          ['door', 'window', 'opening'].includes(state.attributes?.device_class || '')
      )
      .map((state) => state.entity_id)
      .sort();

    return JSON.stringify({ controllers, sensors, climates, windows });
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
    this._activeEntryTitle =
      controller?.attributes?.friendly_name || controller?.entity_id || null;
    return controller;
  }

  _syncViewState() {
    const states = this._getStates();
    const controller = this._getControllerSelection(this._getControllers(states));
    const attrs = controller?.attributes || {};
    const managedClimates = Array.isArray(attrs.managed_climates) ? attrs.managed_climates : [];
    const configuredClimates = attrs.configured_climate_entity_ids || [];
    const sensorOptions = this._getSensorOptions(states);
    const powerOptions = this._getPowerOptions(states);
    const climateOptions = this._getClimateOptions(states);
    const availableClimateOptions = climateOptions.filter(
      (entityId) => !configuredClimates.includes(entityId) && entityId !== controller?.entity_id
    );

    const entryChanged = this._globalDraft?.entry_id !== this._activeEntryId;

    if (!this._globalDraft || entryChanged) {
      this._globalDraft = {
        entry_id: this._activeEntryId,
        forecast_sensor: attrs.forecast_sensor || '',
        production_sensor: attrs.production_sensor || '',
        net_export_sensor: attrs.net_export_sensor || '',
        update_interval_minutes: String(attrs.update_interval_minutes ?? 5),
      };
    }

    if (!this._addDraft || entryChanged) {
      this._addDraft = this._buildAddDraft(availableClimateOptions);
    } else if (
      this._addDraft.entity_id &&
      !availableClimateOptions.includes(this._addDraft.entity_id)
    ) {
      this._addDraft.entity_id = availableClimateOptions[0] || '';
    }

    const activeClimateIds = new Set(managedClimates.map((climate) => climate.entity_id));
    Object.keys(this._climateDrafts).forEach((entityId) => {
      if (!activeClimateIds.has(entityId)) {
        delete this._climateDrafts[entityId];
        if (this._editingClimateId === entityId) {
          this._editingClimateId = null;
        }
      }
    });

    managedClimates.forEach((climate) => {
      if (!this._climateDrafts[climate.entity_id] || entryChanged) {
        this._climateDrafts[climate.entity_id] = this._buildClimateDraft(climate);
      }
    });

    this._viewModel = {
      states,
      controller,
      attrs,
      managedClimates,
      sensorOptions,
      powerOptions,
      climateOptions,
      availableClimateOptions,
      windowOptions: this._getWindowOptions(states),
      criticalErrors: Array.isArray(attrs.critical_input_errors)
        ? attrs.critical_input_errors
        : [],
    };
  }

  _buildAddDraft(availableClimateOptions) {
    return {
      entity_id: availableClimateOptions[0] || '',
      name: '',
      priority: '1',
      enabled: true,
      use_estimated_power: true,
      wattage: '1000',
      power_sensor: '',
      window_sensors: [],
    };
  }

  _buildClimateDraft(climate) {
    return {
      entity_id: climate.entity_id,
      priority: String(climate.priority ?? 1),
      enabled: Boolean(climate.enabled),
      use_estimated_power: Boolean(climate.use_estimated_power),
      wattage: String(climate.estimated_wattage ?? 1000),
      power_sensor: climate.power_sensor || '',
      window_sensors: [...(climate.window_sensors || [])],
    };
  }

  _getSensorOptions(states) {
    return states
      .filter((state) => state.entity_id.startsWith('sensor.'))
      .map((state) => state.entity_id)
      .sort();
  }

  _getPowerOptions(states) {
    return states
      .filter(
        (state) =>
          state.entity_id.startsWith('sensor.') &&
          String(state.attributes?.unit_of_measurement || '')
            .trim()
            .toLowerCase() === 'w'
      )
      .map((state) => state.entity_id)
      .sort();
  }

  _getClimateOptions(states) {
    return states
      .filter((state) => state.entity_id.startsWith('climate.'))
      .map((state) => state.entity_id)
      .sort();
  }

  _getWindowOptions(states) {
    return states
      .filter(
        (state) =>
          state.entity_id.startsWith('binary_sensor.') &&
          ['door', 'window', 'opening'].includes(state.attributes?.device_class || '')
      )
      .map((state) => state.entity_id)
      .sort();
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

  _setNotice(message, tone = 'info') {
    this._notice = message ? { message, tone } : null;
    this._render();
  }

  _clearRefreshTimers() {
    this._refreshTimerIds.forEach((timerId) => {
      window.clearTimeout(timerId);
    });
    this._refreshTimerIds = [];
  }

  _scheduleFollowUpRenders() {
    this._clearRefreshTimers();
    [350, 1000, 2200].forEach((delay) => {
      const timerId = window.setTimeout(() => {
        this._syncViewState();
        this._render();
      }, delay);
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

  _setPending(actionKey, pending) {
    if (pending) {
      this._pendingActions.add(actionKey);
    } else {
      this._pendingActions.delete(actionKey);
    }
    this._render();
  }

  _isPending(actionKey) {
    return this._pendingActions.has(actionKey);
  }

  async _runPanelAction(actionKey, action, successMessage) {
    try {
      this._setPending(actionKey, true);
      await action();
      this._setNotice(successMessage, 'success');
    } catch (error) {
      console.error(error);
      this._setNotice(error?.message || 'Action failed.', 'error');
    } finally {
      this._setPending(actionKey, false);
    }
  }

  _formatBoolean(value, truthyLabel = 'Yes', falsyLabel = 'No') {
    return value ? truthyLabel : falsyLabel;
  }

  _formatDuration(seconds) {
    const totalSeconds = Math.max(Number.parseInt(seconds, 10) || 0, 0);
    const minutes = Math.ceil(totalSeconds / 60);
    if (minutes <= 1) {
      return 'about 1 minute';
    }
    return `about ${minutes} minutes`;
  }

  _rawReasonToText(reason) {
    return String(reason || 'unknown').replaceAll('_', ' ');
  }

  _formatDecisionReason(climate) {
    const reason = climate.reason || 'unknown';

    if (climate.manual_override || reason === 'manual_override') {
      return 'Manual override is active';
    }
    if (!climate.enabled || reason === 'disabled') {
      return 'Automation is turned off for this climate';
    }
    if (climate.windows_open || reason === 'windows_open') {
      return 'Blocked because a configured window or door is open';
    }
    if (reason === 'critical_inputs_invalid') {
      return 'Waiting for valid forecast, production, or export sensor data';
    }
    if (reason.startsWith('minimum_run_time_remaining_')) {
      const seconds = reason.match(/minimum_run_time_remaining_(\d+)s/)?.[1] || '0';
      return `Keeping this unit running for ${this._formatDuration(seconds)}`;
    }
    if (reason.startsWith('minimum_off_time_remaining_')) {
      const seconds = reason.match(/minimum_off_time_remaining_(\d+)s/)?.[1] || '0';
      return `Waiting ${this._formatDuration(seconds)} before restarting`;
    }
    if (reason.includes('running_with_hysteresis')) {
      return 'Cooling remains allowed because surplus is still within the safety margin';
    }
    if (reason.includes('surplus_available_with_hysteresis')) {
      return 'Enough predicted solar surplus is available for this climate';
    }
    if (reason.startsWith('insufficient_surplus_')) {
      const need = reason.match(/need_(-?\d+)W/)?.[1];
      const have = reason.match(/have_(-?\d+)W/)?.[1];
      if (need !== undefined && have !== undefined) {
        return `Not enough predicted solar surplus: needs ${need} W, has ${have} W`;
      }
      return 'Not enough predicted solar surplus is available';
    }
    if (reason.startsWith('priority_')) {
      return 'Running based on current priority order';
    }

    return this._rawReasonToText(reason);
  }

  _getClimateStateBadge(climate) {
    if (climate.manual_override) {
      return { label: 'Manual override', tone: 'warn' };
    }
    if (!climate.enabled) {
      return { label: 'Automation off', tone: 'neutral' };
    }
    if (climate.windows_open) {
      return { label: 'Window open', tone: 'warn' };
    }
    if (climate.reason === 'critical_inputs_invalid') {
      return { label: 'Waiting for sensors', tone: 'danger' };
    }
    if (climate.state === 'cool') {
      return { label: 'Cooling', tone: 'ok' };
    }
    if ((climate.reason || '').startsWith('minimum_off_time_remaining_')) {
      return { label: 'Cooldown', tone: 'neutral' };
    }
    return { label: 'Idle', tone: 'neutral' };
  }

  _renderNotice() {
    if (!this._notice) {
      return '<div class="notice"></div>';
    }

    return `<div class="notice show ${this._escape(this._notice.tone)}">${this._escape(
      this._notice.message
    )}</div>`;
  }

  _renderInstancePicker(controllers) {
    if (controllers.length <= 1) {
      return '';
    }

    return `
      <section class="card compact-card">
        <div class="section-head inline">
          <div>
            <h2>Controller instance</h2>
            <p class="section-copy">Choose which Smart Airco controller you want to manage.</p>
          </div>
          <div class="instance-select-wrap">
            <select id="sel-controller">
              ${controllers
                .map((controller) => {
                  const entryId = controller.attributes?.smart_airco_entry_id || '';
                  const title = controller.attributes?.friendly_name || controller.entity_id;
                  const selected = entryId === this._activeEntryId ? 'selected' : '';
                  return `<option value="${this._escape(entryId)}" ${selected}>${this._escape(
                    title
                  )}</option>`;
                })
                .join('')}
            </select>
          </div>
        </div>
      </section>
    `;
  }

  _renderSetupChecklist(attrs, managedClimates) {
    const items = [
      {
        label: 'Select a forecast sensor',
        done: Boolean(attrs.forecast_sensor),
        hint: 'Choose the forecast entity that exposes the Solcast-style estimate10 attribute expected by Smart Airco.',
      },
      {
        label: 'Select a production sensor',
        done: Boolean(attrs.production_sensor),
        hint: 'Choose your current solar generation sensor in watts.',
      },
      {
        label: 'Select a net export sensor',
        done: Boolean(attrs.net_export_sensor),
        hint: 'Choose the sensor that shows how much power you currently export to the grid.',
      },
      {
        label: 'Add at least one managed climate',
        done: managedClimates.length > 0,
        hint: 'Each managed climate gets its own priority, power settings, and optional window sensors.',
      },
    ];

    const incompleteItems = items.filter((item) => !item.done);
    if (!incompleteItems.length) {
      return `
        <div class="callout success compact-callout">
          <strong>Setup looks complete.</strong>
          Smart Airco has the core sensors it needs and at least one managed climate.
        </div>
      `;
    }

    return `
      <div class="callout warn compact-callout">
        <strong>Finish these setup steps first.</strong>
        <ul class="checklist">
          ${items
            .map(
              (item) => `
                <li class="${item.done ? 'done' : 'todo'}">
                  <span class="checkmark">${item.done ? '✓' : '•'}</span>
                  <div>
                    <div class="check-label">${this._escape(item.label)}</div>
                    <div class="check-hint">${this._escape(item.hint)}</div>
                  </div>
                </li>
              `
            )
            .join('')}
        </ul>
      </div>
    `;
  }

  _renderSetupSection(attrs, sensorOptions, managedClimates) {
    const draft = this._globalDraft || {
      forecast_sensor: '',
      production_sensor: '',
      net_export_sensor: '',
      update_interval_minutes: '5',
    };

    return `
      <section class="card">
        <div class="section-head">
          <div>
            <h2>Setup</h2>
            <p class="section-copy">Choose the core energy sensors Smart Airco uses to decide when there is enough solar surplus to run your climates.</p>
          </div>
          <div class="section-meta">
            <span class="tag neutral">Panel-first setup</span>
          </div>
        </div>
        ${this._renderSetupChecklist(attrs, managedClimates)}
        <div class="field-grid">
          <div class="field-card">
            <label for="sel-forecast">Forecast sensor</label>
            <select id="sel-forecast" data-global-field="forecast_sensor">${this._selectOptions(
              sensorOptions,
              draft.forecast_sensor || ''
            )}</select>
            <p class="field-help">Choose the forecast entity that exposes the <code>estimate10</code> attribute Smart Airco expects. This should match the Solcast entity you already rely on for forecasting.</p>
          </div>
          <div class="field-card">
            <label for="sel-production">Production sensor</label>
            <select id="sel-production" data-global-field="production_sensor">${this._selectOptions(
              sensorOptions,
              draft.production_sensor || ''
            )}</select>
            <p class="field-help">Your live solar generation sensor in watts.</p>
          </div>
          <div class="field-card">
            <label for="sel-netexport">Net export sensor</label>
            <select id="sel-netexport" data-global-field="net_export_sensor">${this._selectOptions(
              sensorOptions,
              draft.net_export_sensor || ''
            )}</select>
            <p class="field-help">How much power you currently export to the grid in watts.</p>
          </div>
          <div class="field-card">
            <label for="inp-interval">Update interval</label>
            <input id="inp-interval" data-global-field="update_interval_minutes" type="number" min="1" max="60" value="${this._escape(
              draft.update_interval_minutes || '5'
            )}" />
            <p class="field-help">How often Smart Airco refreshes sensors and reevaluates decisions. Start with 5 minutes for practical day-to-day use.</p>
          </div>
        </div>
        <div class="button-row">
          <button data-action="save-global" type="button" ${
            this._isPending('save-global') ? 'disabled' : ''
          }>${this._isPending('save-global') ? 'Saving...' : 'Save setup'}</button>
        </div>
      </section>
    `;
  }

  _renderStatusSection(attrs, criticalErrors) {
    const lastUpdate = attrs.last_update ? new Date(attrs.last_update) : null;
    const lastUpdateText = lastUpdate && !Number.isNaN(lastUpdate.getTime())
      ? lastUpdate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : 'Not available yet';

    return `
      <section class="card">
        <div class="section-head">
          <div>
            <h2>System status</h2>
            <p class="section-copy">Live view of Smart Airco's current decision context.</p>
          </div>
        </div>
        <div class="metrics-grid">
          <div class="metric-card"><span class="metric-label">Controller</span><strong>${this._escape(
            attrs.controller_enabled ? 'Enabled' : 'Disabled'
          )}</strong></div>
          <div class="metric-card"><span class="metric-label">Predicted surplus</span><strong>${this._escape(
            attrs.predicted_surplus || 0
          )} W</strong></div>
          <div class="metric-card"><span class="metric-label">Current surplus</span><strong>${this._escape(
            attrs.current_surplus || 0
          )} W</strong></div>
          <div class="metric-card"><span class="metric-label">Running climates</span><strong>${this._escape(
            attrs.running_entities || 0
          )}</strong></div>
          <div class="metric-card"><span class="metric-label">Manual overrides</span><strong>${this._escape(
            attrs.manual_override_entities || 0
          )}</strong></div>
          <div class="metric-card"><span class="metric-label">Last update</span><strong>${this._escape(
            lastUpdateText
          )}</strong></div>
        </div>
        <div class="status-band">
          <span class="status-label">Current summary</span>
          <strong>${this._escape(this._rawReasonToText(attrs.decision_reason || 'unknown'))}</strong>
        </div>
        ${
          criticalErrors.length
            ? `<div class="callout danger compact-callout"><strong>Sensor issue:</strong> ${this._escape(
                criticalErrors.join(', ')
              )}</div>`
            : ''
        }
      </section>
    `;
  }

  _renderActionsSection() {
    return `
      <section class="card compact-card">
        <div class="section-head inline">
          <div>
            <h2>Actions</h2>
            <p class="section-copy">Useful when you want Smart Airco to reevaluate immediately.</p>
          </div>
          <div class="button-row compact-actions">
            <button data-action="evaluate" type="button" ${
              this._isPending('evaluate') ? 'disabled' : ''
            }>${this._isPending('evaluate') ? 'Evaluating...' : 'Evaluate now'}</button>
            <button data-action="execute" type="button" ${
              this._isPending('execute') ? 'disabled' : ''
            }>${this._isPending('execute') ? 'Executing...' : 'Apply decisions'}</button>
          </div>
        </div>
      </section>
    `;
  }

  _renderAddClimateSection(availableClimateOptions, powerOptions) {
    const draft = this._addDraft || this._buildAddDraft(availableClimateOptions);

    return `
      <section class="card compact-card">
        <div class="section-head">
          <div>
            <h2>Add managed climate</h2>
            <p class="section-copy">Add a climate entity and give Smart Airco the information it needs to manage it safely.</p>
          </div>
        </div>
        <div class="field-grid">
          <div class="field-card">
            <label for="add-entity">Climate entity</label>
            <select id="add-entity" data-add-field="entity_id">${this._selectOptions(
              availableClimateOptions,
              draft.entity_id || '',
              availableClimateOptions.length ? '(select climate)' : '(all climates already added)'
            )}</select>
          </div>
          <div class="field-card">
            <label for="add-name">Display name</label>
            <input id="add-name" data-add-field="name" type="text" placeholder="Living Room" value="${this._escape(
              draft.name || ''
            )}" />
          </div>
          <div class="field-card">
            <label for="add-priority">Priority</label>
            <input id="add-priority" data-add-field="priority" type="number" min="1" max="10" value="${this._escape(
              draft.priority || '1'
            )}" />
          </div>
          <div class="field-card field-check">
            <label><input id="add-enabled" data-add-field="enabled" type="checkbox" ${
              draft.enabled ? 'checked' : ''
            } /> Enable automation for this climate</label>
          </div>
          <div class="field-card field-check">
            <label><input id="add-use-estimated" data-add-field="use_estimated_power" type="checkbox" ${
              draft.use_estimated_power ? 'checked' : ''
            } /> Use estimated power</label>
          </div>
          <div class="field-card">
            <label for="add-wattage">Estimated wattage</label>
            <input id="add-wattage" data-add-field="wattage" type="number" min="100" max="5000" value="${this._escape(
              draft.wattage || '1000'
            )}" />
          </div>
          <div class="field-card">
            <label for="add-power-sensor">Power sensor</label>
            <select id="add-power-sensor" data-add-field="power_sensor">${this._selectOptions(
              powerOptions,
              draft.power_sensor || ''
            )}</select>
          </div>
          <div class="field-card">
            <label for="add-window-sensors">Window and door sensors</label>
            <select id="add-window-sensors" data-add-field="window_sensors" multiple>${this._multiSelectOptions(
              this._viewModel.windowOptions,
              draft.window_sensors || []
            )}</select>
            <p class="field-help">Optional. If any selected sensor is open, this climate will be blocked from running automatically.</p>
          </div>
        </div>
        <div class="button-row">
          <button data-action="add-climate" type="button" ${
            this._isPending('add-climate') ? 'disabled' : ''
          }>${this._isPending('add-climate') ? 'Adding...' : 'Add climate'}</button>
        </div>
      </section>
    `;
  }

  _renderClimateList(managedClimates, powerOptions, windowOptions) {
    return `
      <section class="card">
        <div class="section-head">
          <div>
            <h2>Managed climates</h2>
            <p class="section-copy">Review each climate at a glance, then open the editor only for the one you want to change.</p>
          </div>
        </div>
        ${
          managedClimates.length
            ? `<div class="climate-list">${managedClimates
                .map((climate) => this._renderClimateCard(climate, powerOptions, windowOptions))
                .join('')}</div>`
            : '<div class="empty empty-card">No managed climates configured yet.</div>'
        }
      </section>
    `;
  }

  _renderClimateCard(climate, powerOptions, windowOptions) {
    const badge = this._getClimateStateBadge(climate);
    const draft = this._climateDrafts[climate.entity_id] || this._buildClimateDraft(climate);
    const isEditing = this._editingClimateId === climate.entity_id;
    const windowsLabel = climate.window_sensors?.length
      ? `${climate.window_sensors.length} sensor${climate.window_sensors.length === 1 ? '' : 's'}`
      : 'No window sensors';
    const powerLabel = climate.use_estimated_power
      ? `Estimated ${climate.estimated_wattage} W`
      : climate.power_sensor
      ? `Sensor: ${climate.power_sensor}`
      : `Sensor fallback to ${climate.estimated_wattage} W`;

    return `
      <article class="climate-card ${isEditing ? 'editing' : ''}">
        <div class="climate-summary">
          <div class="climate-main">
            <div class="climate-title-row">
              <div>
                <h3>${this._escape(climate.name || climate.entity_id)}</h3>
                <code>${this._escape(climate.entity_id)}</code>
              </div>
              <div class="badge-row">
                <span class="tag ${badge.tone}">${this._escape(badge.label)}</span>
                ${climate.manual_override ? '<span class="tag warn">Manual override</span>' : ''}
              </div>
            </div>
            <div class="climate-meta-grid">
              <div><span class="meta-label">Priority</span><strong>${this._escape(
                climate.priority
              )}</strong></div>
              <div><span class="meta-label">Automation</span><strong>${this._escape(
                climate.enabled ? 'Enabled' : 'Disabled'
              )}</strong></div>
              <div><span class="meta-label">Windows</span><strong>${this._escape(
                climate.windows_open ? 'Open / blocking' : windowsLabel
              )}</strong></div>
              <div><span class="meta-label">Power</span><strong>${this._escape(powerLabel)}</strong></div>
            </div>
            <div class="decision-block">
              <span class="meta-label">Decision</span>
              <strong>${this._escape(this._formatDecisionReason(climate))}</strong>
              <span class="technical-note">Technical reason: ${this._escape(
                this._rawReasonToText(climate.reason || 'unknown')
              )}</span>
            </div>
          </div>
          <div class="climate-actions">
            <label class="toggle-pill">
              <input
                type="checkbox"
                data-action="toggle-climate"
                data-climate-id="${this._escape(climate.entity_id)}"
                ${draft.enabled ? 'checked' : ''}
                ${this._isPending(`toggle:${climate.entity_id}`) ? 'disabled' : ''}
              />
              <span>${
                this._isPending(`toggle:${climate.entity_id}`)
                  ? 'Saving...'
                  : draft.enabled
                  ? 'Automation enabled'
                  : 'Automation disabled'
              }</span>
            </label>
            <button
              data-action="toggle-editor"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="button"
              class="secondary"
            >${isEditing ? 'Close editor' : 'Edit settings'}</button>
          </div>
        </div>
        ${isEditing ? this._renderClimateEditor(climate, draft, powerOptions, windowOptions) : ''}
      </article>
    `;
  }

  _renderClimateEditor(climate, draft, powerOptions, windowOptions) {
    return `
      <div class="editor-panel">
        <div class="editor-grid">
          <section class="editor-section">
            <h4>Automation</h4>
            <label for="priority-${this._escape(climate.entity_id)}">Priority</label>
            <input
              id="priority-${this._escape(climate.entity_id)}"
              data-climate-field="priority"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="number"
              min="1"
              max="10"
              value="${this._escape(draft.priority)}"
            />
            <button
              data-action="save-priority"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="button"
              ${this._isPending(`priority:${climate.entity_id}`) ? 'disabled' : ''}
            >${this._isPending(`priority:${climate.entity_id}`) ? 'Saving...' : 'Save priority'}</button>
          </section>
          <section class="editor-section">
            <h4>Power</h4>
            <label class="checkbox-line">
              <input
                data-climate-field="use_estimated_power"
                data-climate-id="${this._escape(climate.entity_id)}"
                type="checkbox"
                ${draft.use_estimated_power ? 'checked' : ''}
              />
              Use estimated power instead of a live power sensor
            </label>
            <label for="wattage-${this._escape(climate.entity_id)}">Estimated wattage</label>
            <input
              id="wattage-${this._escape(climate.entity_id)}"
              data-climate-field="wattage"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="number"
              min="100"
              max="5000"
              value="${this._escape(draft.wattage)}"
            />
            <label for="power-sensor-${this._escape(climate.entity_id)}">Power sensor</label>
            <select
              id="power-sensor-${this._escape(climate.entity_id)}"
              data-climate-field="power_sensor"
              data-climate-id="${this._escape(climate.entity_id)}"
            >${this._selectOptions(powerOptions, draft.power_sensor || '')}</select>
            <button
              data-action="save-power"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="button"
              ${this._isPending(`power:${climate.entity_id}`) ? 'disabled' : ''}
            >${this._isPending(`power:${climate.entity_id}`) ? 'Saving...' : 'Save power settings'}</button>
          </section>
          <section class="editor-section">
            <h4>Window safety</h4>
            <label for="window-sensors-${this._escape(climate.entity_id)}">Window and door sensors</label>
            <select
              id="window-sensors-${this._escape(climate.entity_id)}"
              data-climate-field="window_sensors"
              data-climate-id="${this._escape(climate.entity_id)}"
              multiple
            >${this._multiSelectOptions(windowOptions, draft.window_sensors || [])}</select>
            <p class="field-help">If any selected sensor is open, this climate is blocked from running automatically.</p>
            <button
              data-action="save-windows"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="button"
              ${this._isPending(`windows:${climate.entity_id}`) ? 'disabled' : ''}
            >${this._isPending(`windows:${climate.entity_id}`) ? 'Saving...' : 'Save window sensors'}</button>
          </section>
          <section class="editor-section danger-zone">
            <h4>Danger zone</h4>
            <p class="field-help">Remove this climate from Smart Airco management. The underlying climate entity itself is not deleted.</p>
            <button
              data-action="remove-climate"
              data-climate-id="${this._escape(climate.entity_id)}"
              type="button"
              class="danger"
              ${this._isPending(`remove:${climate.entity_id}`) ? 'disabled' : ''}
            >${this._isPending(`remove:${climate.entity_id}`) ? 'Removing...' : 'Remove climate'}</button>
          </section>
        </div>
      </div>
    `;
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }

    this._syncViewState();
    const {
      controller,
      attrs,
      managedClimates,
      sensorOptions,
      powerOptions,
      availableClimateOptions,
      windowOptions,
      criticalErrors,
      states,
    } = this._viewModel;
    const controllers = this._getControllers(states);

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          color: var(--primary-text-color);
          background:
            radial-gradient(circle at top right, rgba(14, 165, 233, 0.14), transparent 28%),
            linear-gradient(180deg, rgba(15, 23, 42, 0.05), transparent 22%),
            var(--primary-background-color);
          min-height: 100vh;
        }
        * { box-sizing: border-box; }
        .wrap {
          max-width: 1180px;
          margin: 0 auto;
          padding: 24px;
          font-family: var(--primary-font-family, system-ui, sans-serif);
        }
        .hero {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          margin-bottom: 20px;
          padding: 24px;
          border-radius: 20px;
          background: linear-gradient(135deg, rgba(14, 116, 144, 0.18), rgba(3, 105, 161, 0.08));
          border: 1px solid rgba(125, 211, 252, 0.18);
        }
        .hero h1 {
          margin: 0 0 8px;
          font-size: 1.9rem;
        }
        .hero p {
          margin: 0;
          max-width: 780px;
          opacity: 0.82;
        }
        .hero-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          justify-content: flex-end;
        }
        .card {
          margin-bottom: 18px;
          padding: 20px;
          border-radius: 18px;
          border: 1px solid rgba(148, 163, 184, 0.16);
          background: var(--card-background-color, rgba(255, 255, 255, 0.05));
          box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
        }
        .compact-card {
          padding: 18px;
        }
        .section-head {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          margin-bottom: 16px;
        }
        .section-head.inline {
          align-items: center;
        }
        h2 {
          margin: 0 0 6px;
          font-size: 1.12rem;
        }
        h3 {
          margin: 0 0 6px;
          font-size: 1.1rem;
        }
        h4 {
          margin: 0 0 12px;
          font-size: 0.98rem;
        }
        .section-copy {
          margin: 0;
          color: var(--secondary-text-color);
          max-width: 760px;
        }
        .section-meta,
        .instance-select-wrap {
          flex-shrink: 0;
        }
        .field-grid,
        .metrics-grid,
        .editor-grid {
          display: grid;
          gap: 14px;
        }
        .field-grid {
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }
        .metrics-grid {
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          margin-bottom: 14px;
        }
        .editor-grid {
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }
        .field-card,
        .metric-card,
        .editor-section {
          padding: 14px;
          border-radius: 14px;
          background: rgba(148, 163, 184, 0.07);
          border: 1px solid rgba(148, 163, 184, 0.12);
        }
        .field-check {
          display: flex;
          align-items: center;
        }
        .metric-label,
        .meta-label {
          display: block;
          margin-bottom: 6px;
          font-size: 0.78rem;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: var(--secondary-text-color);
        }
        .metric-card strong,
        .decision-block strong,
        .meta-grid strong {
          display: block;
          font-size: 1rem;
        }
        .status-band {
          padding: 14px 16px;
          border-radius: 14px;
          border: 1px solid rgba(148, 163, 184, 0.14);
          background: rgba(14, 165, 233, 0.08);
        }
        label {
          display: block;
          margin-bottom: 8px;
          font-weight: 600;
        }
        .checkbox-line,
        .toggle-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-weight: 500;
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
        select,
        textarea {
          padding: 11px 12px;
          border-radius: 12px;
          border: 1px solid rgba(148, 163, 184, 0.25);
          background: rgba(15, 23, 42, 0.08);
        }
        input[type='checkbox'] {
          width: auto;
          margin: 0;
        }
        select[multiple] {
          min-height: 140px;
        }
        button {
          padding: 11px 14px;
          border-radius: 12px;
          border: 1px solid rgba(14, 165, 233, 0.22);
          background: rgba(14, 165, 233, 0.14);
          cursor: pointer;
          transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
        }
        button:hover:not(:disabled) {
          background: rgba(14, 165, 233, 0.22);
          transform: translateY(-1px);
        }
        button.secondary {
          background: rgba(148, 163, 184, 0.1);
          border-color: rgba(148, 163, 184, 0.2);
        }
        button.danger {
          background: rgba(220, 38, 38, 0.12);
          border-color: rgba(220, 38, 38, 0.24);
        }
        button:disabled,
        input:disabled,
        select:disabled {
          opacity: 0.65;
          cursor: not-allowed;
          transform: none;
        }
        .button-row {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          margin-top: 16px;
        }
        .compact-actions {
          margin-top: 0;
        }
        .tag {
          display: inline-flex;
          align-items: center;
          padding: 5px 10px;
          border-radius: 999px;
          border: 1px solid rgba(148, 163, 184, 0.2);
          font-size: 0.82rem;
          background: rgba(148, 163, 184, 0.12);
        }
        .tag.ok {
          background: rgba(22, 163, 74, 0.14);
          border-color: rgba(22, 163, 74, 0.25);
        }
        .tag.warn {
          background: rgba(217, 119, 6, 0.16);
          border-color: rgba(217, 119, 6, 0.28);
        }
        .tag.danger {
          background: rgba(220, 38, 38, 0.16);
          border-color: rgba(220, 38, 38, 0.28);
        }
        .tag.neutral {
          background: rgba(148, 163, 184, 0.12);
        }
        .notice {
          display: none;
          margin-bottom: 16px;
          padding: 12px 14px;
          border-radius: 14px;
          border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .notice.show {
          display: block;
        }
        .notice.info {
          background: rgba(59, 130, 246, 0.12);
        }
        .notice.success,
        .callout.success {
          background: rgba(22, 163, 74, 0.12);
        }
        .notice.error,
        .callout.danger {
          background: rgba(220, 38, 38, 0.14);
        }
        .callout.warn {
          background: rgba(217, 119, 6, 0.12);
        }
        .callout {
          padding: 14px 16px;
          border-radius: 14px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          margin-bottom: 16px;
        }
        .compact-callout {
          margin-top: 0;
        }
        .checklist {
          margin: 12px 0 0;
          padding: 0;
          list-style: none;
          display: grid;
          gap: 10px;
        }
        .checklist li {
          display: grid;
          grid-template-columns: 20px 1fr;
          gap: 10px;
        }
        .check-label {
          font-weight: 600;
        }
        .check-hint,
        .field-help,
        .technical-note,
        .empty {
          color: var(--secondary-text-color);
        }
        .field-help,
        .technical-note,
        .check-hint {
          font-size: 0.9rem;
          margin: 8px 0 0;
          line-height: 1.4;
        }
        .climate-list {
          display: grid;
          gap: 14px;
        }
        .climate-card {
          border: 1px solid rgba(148, 163, 184, 0.16);
          border-radius: 16px;
          background: rgba(15, 23, 42, 0.03);
          overflow: hidden;
        }
        .climate-card.editing {
          border-color: rgba(14, 165, 233, 0.3);
          box-shadow: 0 0 0 1px rgba(14, 165, 233, 0.16);
        }
        .climate-summary {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 220px;
          gap: 16px;
          padding: 18px;
        }
        .climate-title-row {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          margin-bottom: 14px;
        }
        .badge-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }
        .climate-meta-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 12px;
          margin-bottom: 14px;
        }
        .decision-block {
          padding: 12px 14px;
          border-radius: 14px;
          background: rgba(148, 163, 184, 0.07);
          border: 1px solid rgba(148, 163, 184, 0.12);
        }
        .climate-actions {
          display: flex;
          flex-direction: column;
          gap: 10px;
          align-items: stretch;
        }
        .toggle-pill {
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          background: rgba(148, 163, 184, 0.08);
          justify-content: center;
        }
        .editor-panel {
          padding: 0 18px 18px;
        }
        .danger-zone {
          align-self: start;
        }
        .empty-card {
          padding: 16px;
          border-radius: 14px;
          background: rgba(148, 163, 184, 0.07);
          border: 1px solid rgba(148, 163, 184, 0.12);
        }
        code {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.9rem;
          word-break: break-word;
        }
        @media (max-width: 1024px) {
          .climate-summary {
            grid-template-columns: 1fr;
          }
          .climate-actions {
            flex-direction: row;
            flex-wrap: wrap;
          }
          .climate-actions > * {
            flex: 1 1 220px;
          }
        }
        @media (max-width: 900px) {
          .wrap {
            padding: 16px;
          }
          .hero,
          .section-head,
          .section-head.inline,
          .climate-title-row {
            flex-direction: column;
          }
          .field-grid,
          .metrics-grid,
          .editor-grid,
          .climate-meta-grid {
            grid-template-columns: 1fr;
          }
          .hero-meta,
          .badge-row {
            justify-content: flex-start;
          }
        }
      </style>
      <div class="wrap">
        <section class="hero">
          <div>
            <h1>Smart Airco</h1>
            <p>Manage your solar-aware climates from one place with clearer setup guidance, live system context, and focused climate editors.</p>
          </div>
          <div class="hero-meta">
            <span class="tag neutral">${this._escape(this._activeEntryTitle || 'No controller')}</span>
            <span class="tag ${attrs.controller_enabled ? 'ok' : 'neutral'}">${this._escape(
              attrs.controller_enabled ? 'Controller enabled' : 'Controller disabled'
            )}</span>
          </div>
        </section>
        ${this._renderNotice()}
        ${this._renderInstancePicker(controllers)}
        ${this._renderSetupSection(attrs, sensorOptions, managedClimates)}
        ${this._renderStatusSection(attrs, criticalErrors)}
        ${this._renderActionsSection()}
        ${this._renderAddClimateSection(availableClimateOptions, powerOptions)}
        ${this._renderClimateList(managedClimates, powerOptions, windowOptions)}
      </div>
    `;
  }

  _handleInput(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.hasAttribute('data-global-field')) {
      const field = target.getAttribute('data-global-field');
      if (field && this._globalDraft) {
        this._globalDraft[field] = target.type === 'checkbox' ? target.checked : target.value;
      }
      return;
    }

    if (target.hasAttribute('data-add-field')) {
      const field = target.getAttribute('data-add-field');
      if (field && this._addDraft) {
        if (target instanceof HTMLSelectElement && target.multiple) {
          this._addDraft[field] = Array.from(target.selectedOptions).map((option) => option.value);
          return;
        }
        this._addDraft[field] = target.type === 'checkbox' ? target.checked : target.value;
      }
      return;
    }

    if (target.hasAttribute('data-climate-field')) {
      const entityId = target.getAttribute('data-climate-id');
      const field = target.getAttribute('data-climate-field');
      if (!entityId || !field || !this._climateDrafts[entityId]) {
        return;
      }
      if (target instanceof HTMLSelectElement && target.multiple) {
        this._climateDrafts[entityId][field] = Array.from(target.selectedOptions).map(
          (option) => option.value
        );
        return;
      }
      this._climateDrafts[entityId][field] =
        target.type === 'checkbox' ? target.checked : target.value;
    }
  }

  _handleChange(event) {
    this._handleInput(event);

    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.id === 'sel-controller') {
      this._activeEntryId = target.value || null;
      this._activeEntryTitle = null;
      this._editingClimateId = null;
      this._renderSignature = null;
      this._notice = null;
      this._syncViewState();
      this._render();
    }
  }

  async _handleClick(event) {
    const button = event.target instanceof Element ? event.target.closest('[data-action]') : null;
    if (!button) {
      return;
    }

    const action = button.getAttribute('data-action');
    const climateId = button.getAttribute('data-climate-id');

    if (action === 'toggle-editor') {
      this._editingClimateId = this._editingClimateId === climateId ? null : climateId;
      this._render();
      return;
    }

    if (action === 'evaluate') {
      await this._runPanelAction('evaluate', async () => {
        await this._callSmartAircoService('evaluate_conditions');
      }, 'Condition evaluation requested.');
      return;
    }

    if (action === 'execute') {
      await this._runPanelAction('execute', async () => {
        await this._callSmartAircoService('execute_decisions');
      }, 'Decision execution requested.');
      return;
    }

    if (action === 'save-global') {
      const draft = this._globalDraft || {};
      const updateIntervalMinutes = Number.parseInt(draft.update_interval_minutes || '5', 10);
      await this._runPanelAction('save-global', async () => {
        await this._callSmartAircoService('set_global_settings', {
          forecast_sensor: draft.forecast_sensor || null,
          production_sensor: draft.production_sensor || null,
          net_export_sensor: draft.net_export_sensor || null,
          update_interval_minutes: Number.isFinite(updateIntervalMinutes)
            ? updateIntervalMinutes
            : 5,
        });
      }, 'Setup saved.');
      return;
    }

    if (action === 'add-climate') {
      const draft = this._addDraft || this._buildAddDraft([]);
      if (!draft.entity_id) {
        this._setNotice('Select a climate entity before adding it.', 'error');
        return;
      }
      const priority = Number.parseInt(draft.priority || '1', 10);
      const wattage = Number.parseInt(draft.wattage || '1000', 10);
      await this._runPanelAction('add-climate', async () => {
        const payload = {
          entity_id: draft.entity_id,
          priority: Number.isFinite(priority) ? priority : 1,
          enabled: Boolean(draft.enabled),
          use_estimated_power: Boolean(draft.use_estimated_power),
          wattage: Number.isFinite(wattage) ? wattage : 1000,
        };
        if (draft.name) {
          payload.name = draft.name.trim();
        }
        if (draft.power_sensor) {
          payload.power_sensor = draft.power_sensor;
        }
        if (draft.window_sensors?.length) {
          payload.window_sensors = draft.window_sensors;
        }
        await this._callSmartAircoService('add_climate', payload);
        this._addDraft = this._buildAddDraft(this._viewModel.availableClimateOptions || []);
      }, 'Climate added.');
      return;
    }

    if (!climateId) {
      return;
    }

    const draft = this._climateDrafts[climateId];
    if (!draft) {
      return;
    }

    if (action === 'toggle-climate') {
      await this._runPanelAction(`toggle:${climateId}`, async () => {
        await this._callSmartAircoService('toggle_climate_entity', {
          entity_id: climateId,
          enabled: Boolean(draft.enabled),
        });
      }, draft.enabled ? 'Automation enabled for this climate.' : 'Automation disabled for this climate.');
      return;
    }

    if (action === 'save-priority') {
      const priority = Number.parseInt(draft.priority || '1', 10);
      if (!Number.isFinite(priority)) {
        this._setNotice('Priority must be a valid number.', 'error');
        return;
      }
      await this._runPanelAction(`priority:${climateId}`, async () => {
        await this._callSmartAircoService('set_climate_priority', {
          entity_id: climateId,
          priority,
        });
      }, 'Priority updated.');
      return;
    }

    if (action === 'save-power') {
      const wattage = Number.parseInt(draft.wattage || '1000', 10);
      await this._runPanelAction(`power:${climateId}`, async () => {
        await this._callSmartAircoService('set_climate_power', {
          entity_id: climateId,
          use_estimated_power: Boolean(draft.use_estimated_power),
          wattage: Number.isFinite(wattage) ? wattage : 1000,
          power_sensor: draft.power_sensor || null,
        });
      }, 'Power settings updated.');
      return;
    }

    if (action === 'save-windows') {
      await this._runPanelAction(`windows:${climateId}`, async () => {
        await this._callSmartAircoService('set_climate_windows', {
          entity_id: climateId,
          window_sensors: draft.window_sensors || [],
        });
      }, 'Window sensors updated.');
      return;
    }

    if (action === 'remove-climate') {
      await this._runPanelAction(`remove:${climateId}`, async () => {
        await this._callSmartAircoService('remove_climate', {
          entity_id: climateId,
        });
        if (this._editingClimateId === climateId) {
          this._editingClimateId = null;
        }
      }, 'Climate removed.');
    }
  }
}

if (!customElements.get('smart-airco-panel')) {
  customElements.define('smart-airco-panel', SmartAircoPanel);
}
