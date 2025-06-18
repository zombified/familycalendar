function calendar_sync(baseurl) {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", baseurl+"/sync", false);
  xhr.onload = function() {
    if(xhr.status !== 200) {
      console.log("problem with sync endpoint: ", xhr.status);
      return
    }
    console.log("all synced up");
  };
  xhr.onerror = function() {
    console.log("uh oh, failed to sync");
  };
  xhr.send();
}

function calendar_refresh() {
  ec.refetchEvents();
}

function calendar_update(baseurl) {
  calendar_sync(baseurl);
  calendar_refresh();
}

function calendar_auto_daynight(auto_daynight, daystart, dayend) {
  if(!auto_daynight) {
    return;
  }
  let hr = (new Date()).getHours();
  if(hr >= daystart && hr <= dayend) {
    // day mode
    document.body.classList.remove("ec-dark")
  }
  else {
    // night mode
    document.body.classList.add("ec-dark")
  }
}
