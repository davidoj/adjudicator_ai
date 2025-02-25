/**
 * AnalysisManager - Main controller class for debate analysis
 * Handles the entire analysis process flow and UI updates
 */
class AnalysisManager {
  constructor(config = {}) {
    // Default configuration
    this.config = {
      formSelector: 'form.analysis-form',
      loadingOverlayId: 'loading-overlay',
      progressBarId: 'progress-bar',
      progressStatusId: 'progress-status',
      loadingTextSelector: '.loading-text',
      retryNoticeId: 'retry-notice',
      retryCountId: 'retry-count',
      previewElements: {},
      resultsElements: {},
      creditCheck: null,
      ...config
    };
    
    // Application state
    this.state = {
      isLoading: false,
      progress: 0,
      stage: 'idle',
      currentStep: '',
      retryCount: 0,
      analysisData: null,
      error: null
    };
    
    this.eventSource = null;
    this.domElements = this.cacheDOMElements();
    this.bindEvents();
  }
  
  /**
   * Cache DOM elements for better performance
   */
  cacheDOMElements() {
    const elements = {
      form: document.querySelector(this.config.formSelector),
      loadingOverlay: document.getElementById(this.config.loadingOverlayId),
      loadingText: document.querySelector(this.config.loadingTextSelector),
      progressBar: document.getElementById(this.config.progressBarId),
      progressStatus: document.getElementById(this.config.progressStatusId),
      retryNotice: document.getElementById(this.config.retryNoticeId),
      retryCount: document.getElementById(this.config.retryCountId),
      submitButton: document.querySelector(`${this.config.formSelector} button[type="submit"]`),
      previewElements: {},
      resultsElements: {}
    };
    
    console.log('Form found:', elements.form); // Check if null or an actual element
    
    // Cache preview elements
    if (this.config.previewElements) {
      for (const [key, ids] of Object.entries(this.config.previewElements)) {
        elements.previewElements[key] = {
          container: document.getElementById(ids.container),
          content: document.getElementById(ids.content)
        };
      }
    }
    
    // Cache results elements
    if (this.config.resultsElements) {
      const resultsConfig = this.config.resultsElements;
      elements.resultsElements = {
        container: document.getElementById(resultsConfig.container)
      };
      
      for (const [key, id] of Object.entries(resultsConfig)) {
        if (key !== 'container') {
          elements.resultsElements[key] = document.getElementById(id);
        }
      }
    }
    
    return elements;
  }
  
  /**
   * Bind event listeners
   */
  bindEvents() {
    if (this.domElements.form) {
      this.domElements.form.addEventListener('submit', this.handleSubmit.bind(this));
    }
    
    // Add window beforeunload event to prevent accidental navigation during analysis
    window.addEventListener('beforeunload', (e) => {
      if (this.state.isLoading) {
        e.preventDefault();
        e.returnValue = 'Analysis in progress. Are you sure you want to leave?';
        return e.returnValue;
      }
    });
  }
  
  /**
   * Handle form submission
   */
  handleSubmit(e) {
    console.log('handleSubmit called');
    e.preventDefault();
    
    // Check credits if configured
    if (this.config.creditCheck) {
      const { available, minimum, message } = this.config.creditCheck;
      if (available < minimum) {
        alert(message);
        return;
      }
    }
    
    const formData = new FormData(e.target);
    this.startAnalysis(formData);
  }
  
  /**
   * Start the analysis process
   */
  startAnalysis(formData) {
    if (this.state.isLoading) return;
    
    // Update state
    this.updateState({
      isLoading: true,
      progress: 0,
      stage: 'starting',
      error: null,
      analysisData: null
    });
    
    // Update UI
    this.updateUI();
    
    // Disable form submission
    if (this.domElements.submitButton) {
      this.domElements.submitButton.disabled = true;
    }
    
    // Create EventSource for server-sent events
    this.connectToEventSource(formData);
  }
  
  /**
   * Connect to the server's event stream
   */
  connectToEventSource(formData) {
    // Close any existing connection
    if (this.eventSource) {
      this.eventSource.close();
    }
    
    // First, send the form data via POST
    fetch('/analyze-stream/', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
      }
    })
    .then(response => {
      console.log('Response status:', response.status);
      if (!response.ok) {
        return response.json().then(data => {
          console.log('Error response data:', data);
          throw new Error(data.error || 'Network response was not ok');
        });
      }
      
      // Now create the EventSource to listen for updates
      this.eventSource = new EventSource('/analyze-stream/');
      
      // Set up event handlers
      this.eventSource.onopen = this.handleEventSourceOpen.bind(this);
      this.eventSource.onerror = this.handleEventSourceError.bind(this);
      this.eventSource.onmessage = this.handleEventSourceMessage.bind(this);
    })
    .catch(error => {
      console.error('Caught error:', error);
      this.updateState({
        error: error.message,
        isLoading: false
      });
      this.updateUI();
      
      // Re-enable form submission
      if (this.domElements.submitButton) {
        this.domElements.submitButton.disabled = false;
      }
    });
  }
  
  /**
   * Handle EventSource open event
   */
  handleEventSourceOpen(e) {
    console.log('Connection to analysis stream established');
  }
  
  /**
   * Handle EventSource error
   */
  handleEventSourceError(e) {
    console.error('Error with EventSource connection:', e);
    
    // Only update state if we're still loading (avoid overwriting completion)
    if (this.state.isLoading) {
      this.updateState({
        error: 'Connection to server lost. Please try again.',
        isLoading: false
      });
      this.updateUI();
    }
    
    // Close the connection
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    
    // Re-enable form submission
    if (this.domElements.submitButton) {
      this.domElements.submitButton.disabled = false;
    }
  }
  
  /**
   * Handle generic EventSource messages
   */
  handleEventSourceMessage(e) {
    try {
      const data = JSON.parse(e.data);
      console.log('Received message:', data);
      
      // Skip heartbeat messages
      if (data.heartbeat) return;
      
      // Process different message types
      if (data.status === 'complete' || data.stage === 'complete') {
        this.handleCompleteEvent(data);
      } else if (data.status === 'error' || data.stage === 'error') {
        this.handleErrorEvent(data);
      } else {
        this.processMessageData(data);
      }
    } catch (error) {
      console.error('Error parsing message:', error, e.data);
    }
  }
  
  /**
   * Handle completion events
   */
  handleCompleteEvent(data) {
    console.log('Analysis complete:', data);
    
    // Store redirect URL and debate ID in localStorage
    if (data.redirect) {
      localStorage.setItem('last_redirect_url', data.redirect);
    }
    
    if (data.debate_id) {
      localStorage.setItem('last_debate_id', String(data.debate_id));
    }
    
    // Update state
    this.updateState({
      isLoading: false,
      progress: 100,
      stage: 'complete',
      currentStep: 'Analysis complete!'
    });
    
    this.updateUI();
    
    // Close the connection
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    
    // Redirect after a short delay
    if (data.redirect) {
      setTimeout(() => {
        window.location.href = data.redirect;
      }, 1000);
    }
  }
  
  /**
   * Handle error events
   */
  handleErrorEvent(data) {
    this.updateState({
      error: data.message || 'An error occurred during analysis',
      isLoading: false
    });
    
    // Update progress bar to error state
    if (this.domElements.progressBar) {
      this.domElements.progressBar.style.backgroundColor = '#dc3545';
    }
    
    this.updateUI();
    
    // Close the connection
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    
    // Re-enable form submission
    if (this.domElements.submitButton) {
      this.domElements.submitButton.disabled = false;
    }
  }
  
  /**
   * Process message data and update state accordingly
   */
  processMessageData(data) {
    // Update progress if available
    if (data.percent !== undefined) {
      this.updateState({
        progress: data.percent
      });
    }
    
    // Update message if available
    if (data.message) {
      this.updateState({
        currentStep: data.message
      });
    }
    
    // Update stage if available
    if (data.stage) {
      this.updateState({
        stage: data.stage
      });
    }
    
    // Handle snippets/preview data
    if (data.snippets) {
      this.updatePreviews(data.snippets);
    }
    
    // Handle specific stages
    switch(data.stage) {
      case 'title_extracted':
      case 'initial_analysis':
        if (data.belligerent_1 && this.domElements.resultsElements.belligerent1) {
          this.domElements.resultsElements.belligerent1.textContent = data.belligerent_1;
        }
        if (data.belligerent_2 && this.domElements.resultsElements.belligerent2) {
          this.domElements.resultsElements.belligerent2.textContent = data.belligerent_2;
        }
        if (data.summary_1 && this.domElements.resultsElements.summary1) {
          this.domElements.resultsElements.summary1.textContent = data.summary_1;
        }
        if (data.summary_2 && this.domElements.resultsElements.summary2) {
          this.domElements.resultsElements.summary2.textContent = data.summary_2;
        }
        
        // Also update the participants preview
        if (this.domElements.previewElements.participants) {
          this.domElements.previewElements.participants.container.style.display = 'block';
          this.domElements.previewElements.participants.content.textContent = 
            `${data.belligerent_1}: ${data.summary_1}\n\n${data.belligerent_2}: ${data.summary_2}`;
        }
        break;
        
      case 'retrying':
        this.updateState({
          retryCount: data.attempt || (this.state.retryCount + 1)
        });
        break;
    }
    
    this.updateUI();
  }
  
  /**
   * Update preview sections with new data
   */
  updatePreviews(snippets) {
    for (const [key, value] of Object.entries(snippets)) {
      if (this.domElements.previewElements[key]) {
        const { container, content } = this.domElements.previewElements[key];
        if (container && content) {
          container.style.display = 'block';
          content.textContent = value;
        }
      }
    }
  }
  
  /**
   * Update internal state
   */
  updateState(newState) {
    this.state = { ...this.state, ...newState };
  }
  
  /**
   * Update UI based on current state
   */
  updateUI() {
    // Show/hide loading overlay
    if (this.domElements.loadingOverlay) {
      this.domElements.loadingOverlay.style.display = this.state.isLoading ? 'flex' : 'none';
    }
    
    // Update loading text
    if (this.domElements.loadingText) {
      this.domElements.loadingText.textContent = this.state.currentStep || this.getStageText();
    }
    
    // Update progress bar
    if (this.domElements.progressBar) {
      this.domElements.progressBar.style.width = `${this.state.progress}%`;
      this.domElements.progressBar.setAttribute('aria-valuenow', this.state.progress);
    }
    
    // Update progress status
    if (this.domElements.progressStatus) {
      this.domElements.progressStatus.textContent = this.state.currentStep || this.getStageText();
    }
    
    // Show/hide retry notice
    if (this.domElements.retryNotice) {
      this.domElements.retryNotice.style.display = this.state.retryCount > 0 ? 'block' : 'none';
      
      if (this.domElements.retryCount) {
        this.domElements.retryCount.textContent = `Attempt ${this.state.retryCount + 1}`;
      }
    }
    
    // Show/hide results container
    if (this.domElements.resultsElements && this.domElements.resultsElements.container) {
      this.domElements.resultsElements.container.style.display = this.state.isLoading ? 'block' : 'none';
    }
    
    // Display error if present
    if (this.state.error) {
      if (this.domElements.progressStatus) {
        this.domElements.progressStatus.textContent = this.state.error;
      }
      
      if (this.domElements.loadingText) {
        this.domElements.loadingText.textContent = 'Error';
      }
    }
  }
  
  /**
   * Get text description for current stage
   */
  getStageText() {
    switch(this.state.stage) {
      case 'starting':
        return 'Starting analysis...';
      case 'extracting':
      case 'title_extracted':
        return 'Extracting debate information...';
      case 'analyzing':
      case 'analysis':
      case 'initial_analysis':
        return 'Analyzing arguments...';
      case 'evaluating':
      case 'evaluation':
        return 'Evaluating debate quality...';
      case 'judging':
      case 'judgment':
        return 'Determining winner...';
      case 'formatting':
        return 'Formatting results...';
      case 'saving':
        return 'Saving results...';
      case 'complete':
        return 'Analysis complete!';
      default:
        return 'Processing...';
    }
  }
} 